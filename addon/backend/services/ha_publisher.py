"""
HA Publisher — periodically pushes irrigation state to Home Assistant entities.

All constants and configuration are defined at the top of the file.
Status labels are defined inline (not loaded from JSON files) to avoid
Docker path issues — the frontend dist bundle doesn't preserve the
original public/locales/ directory structure.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import aiohttp
from sqlmodel import Session, select

from backend.config import settings
from backend.constants import RAIN_WEATHER_STATES
from backend.database.db import engine
from backend.models import (
    AppSetting, Schedule, Sensor, SensorType, SkipReason, Zone,
)
from backend.services import ha_client, irrigation
from backend.services import scheduler as sched
from backend.services.irrigation import check_sensors_blocking

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------
_running: bool = False
_publisher_task: Optional[asyncio.Task] = None

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------
PUBLISH_INTERVAL: int = 10  # seconds between HA pushes
INTEGRATION_TAG: str = "irrigation_bss"

# Status labels per language — kept inline because the backend runs inside
# a Docker container where the frontend locale JSON files are not available
# at their original paths (they are bundled into /app/frontend/dist/).
STATUS_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "active":             "Watering",
        "planned":            "Planned",
        "rain_blocked":       "Blocked — rain",
        "rain_today_blocked": "Blocked — rained today",
        "frost_protection":   "Blocked — frost",
        "inactive":           "Pending",
        "friendly_name":      "Irrigation BSS — Watering Status",
    },
    "pl": {
        "active":             "W trakcie",
        "planned":            "Planowane",
        "rain_blocked":       "Zablokowane — deszcz",
        "rain_today_blocked": "Zablokowane — padało dziś",
        "frost_protection":   "Zablokowane — mróz",
        "inactive":           "Oczekuje",
        "friendly_name":      "Irrigation BSS — Status podlewania",
    },
    "de": {
        "active":             "Bewässert",
        "planned":            "Geplant",
        "rain_blocked":       "Blockiert — Regen",
        "rain_today_blocked": "Blockiert — heute geregnet",
        "frost_protection":   "Blockiert — Frost",
        "inactive":           "Ausstehend",
        "friendly_name":      "Irrigation BSS — Bewässerungsstatus",
    },
}

# Map machine_state -> mdi icon
STATE_ICONS: dict[str, str] = {
    "active":             "mdi:sprinkler",
    "planned":            "mdi:calendar-clock",
    "rain_blocked":       "mdi:weather-rainy",
    "rain_today_blocked": "mdi:weather-rainy",
    "frost_protection":   "mdi:snowflake",
    "inactive":           "mdi:sprinkler-variant",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _label(machine_state: str, lang: str) -> str:
    """Get a translated label for a machine state."""
    labels = STATUS_LABELS.get(lang, STATUS_LABELS["en"])
    return labels.get(machine_state, labels.get("inactive", machine_state))


def _friendly_name(lang: str) -> str:
    """Get the translated friendly_name for the status sensor."""
    labels = STATUS_LABELS.get(lang, STATUS_LABELS["en"])
    return labels.get("friendly_name", "Irrigation BSS — Watering Status")


def _icon(machine_state: str) -> str:
    """Get the MDI icon for a machine state."""
    return STATE_ICONS.get(machine_state, "mdi:sprinkler-variant")


async def _push_state(
    session: aiohttp.ClientSession,
    entity_id: str,
    state: str,
    attributes: dict,
) -> None:
    """POST a single entity state to HA REST API."""
    url = f"{settings.ha_url}/api/states/{entity_id}"
    headers = {
        "Authorization": f"Bearer {settings.ha_token}",
        "Content-Type": "application/json",
    }
    try:
        async with session.post(
            url, json={"state": state, "attributes": attributes},
            headers=headers, timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status not in (200, 201):
                logger.warning(f"HA push failed for {entity_id}: HTTP {resp.status}")
    except Exception as e:
        logger.debug(f"HA push error for {entity_id}: {e}")


def _get_language_sync() -> str:
    """Read current UI language from DB (runs in thread)."""
    lang = settings.default_language
    try:
        with Session(engine) as session:
            row = session.get(AppSetting, "app_language")
            if row and row.value:
                lang = row.value
    except Exception:
        pass
    return lang


def _get_db_data_sync() -> tuple[Optional[str], Optional[str], list[dict], dict]:
    """Read next_run, planned_zone_name, all zones, and next schedule skips from DB (runs in thread)."""
    with Session(engine) as session:
        all_zones = session.exec(select(Zone)).all()
        zones_data = [{"id": z.id, "name": z.name} for z in all_zones]
        zone_dict = {z.id: z.name for z in all_zones}

        schedules = session.exec(
            select(Schedule).where(Schedule.enabled == True)
        ).all()
        
        runs = []
        for s in schedules:
            run_iso = sched.get_next_run(s.id)
            if run_iso:
                runs.append((run_iso, zone_dict.get(s.zone_id, "Unknown"), {
                    "skip_if_raining": s.skip_if_raining,
                    "skip_if_rained_today": s.skip_if_rained_today,
                    "skip_if_soil_wet": s.skip_if_soil_wet,
                    "skip_if_frost": s.skip_if_frost,
                }))
        
        next_run = None
        planned_zone_name = None
        skips = {
            "skip_if_raining": False, 
            "skip_if_rained_today": False, 
            "skip_if_soil_wet": False, 
            "skip_if_frost": False
        }
        
        if runs:
            runs.sort(key=lambda x: x[0])
            next_run = runs[0][0]
            planned_zone_name = runs[0][1]
            skips = runs[0][2]

    return next_run, planned_zone_name, zones_data, skips


# ---------------------------------------------------------------------------
# State resolution
# ---------------------------------------------------------------------------
def _resolve_machine_state(
    active_zones: list[dict],
    rain_blocked: bool,
    frost_blocked: bool,
    next_run: Optional[str],
) -> str:
    """Determine the machine_state string from current conditions."""
    if active_zones:
        return "active"
    if rain_blocked:
        return "rain_blocked"
    if frost_blocked:
        return "frost_protection"
    
    if next_run:
        try:
            dt = datetime.fromisoformat(next_run)
            if dt.date() == datetime.now().astimezone().date():
                return "planned"
        except ValueError:
            pass

    return "inactive"


def _get_display_state(
    machine_state: str,
    lang: str,
    active_zone_name: Optional[str] = None,
    planned_zone_name: Optional[str] = None,
) -> str:
    """Build the human-readable display state."""
    label = _label(machine_state, lang)
    if machine_state == "active" and active_zone_name:
        return f"{label} {active_zone_name}"
    if machine_state == "planned" and planned_zone_name:
        return f"{label} {planned_zone_name}"
    return label


# ---------------------------------------------------------------------------
# Entity builders
# ---------------------------------------------------------------------------
def _build_core_entities(
    active_zones: list[dict],
    any_watering: bool,
    machine_state: str,
    display_state: str,
    dynamic_icon: str,
    skip: Optional[SkipReason],
    next_run: Optional[str],
    lang: str,
) -> list[tuple[str, str, dict]]:
    """Build the list of core (non-zone) HA entities."""
    active_zone = active_zones[0] if active_zones else None

    return [
        ("binary_sensor.irrigation_bss_watering", "on" if any_watering else "off", {
            "friendly_name": "Irrigation BSS — Watering Active",
            "device_class": "running",
            "icon": "mdi:sprinkler-variant",
            "integration": INTEGRATION_TAG,
        }),
        ("sensor.irrigation_bss_watering_status", display_state, {
            "friendly_name": _friendly_name(lang),
            "icon": dynamic_icon,
            "integration": INTEGRATION_TAG,
            "status_reason": skip.value if skip else None,
            "state_value": machine_state,
            "active": any_watering,
            "active_zone": active_zone["zone_name"] if active_zone else None,
            "remaining_sec": active_zone["remaining_sec"] if active_zone else 0,
            "next_run": next_run or None,
            "status_text": display_state,
        }),
        ("sensor.irrigation_bss_active_zone",
         active_zone["zone_name"] if active_zone else "idle", {
             "friendly_name": "Irrigation BSS — Active Zone",
             "icon": "mdi:layers",
             "integration": INTEGRATION_TAG,
         }),
        ("sensor.irrigation_bss_remaining_sec",
         str(active_zone["remaining_sec"]) if active_zone else "0", {
             "friendly_name": "Irrigation BSS — Remaining Time",
             "unit_of_measurement": "s",
             "icon": "mdi:timer-outline",
             "integration": INTEGRATION_TAG,
         }),
        ("sensor.irrigation_bss_next_watering", next_run or "unknown", {
            "friendly_name": "Irrigation BSS — Next Watering",
            "device_class": "timestamp",
            "icon": "mdi:calendar-clock",
            "integration": INTEGRATION_TAG,
        }),
        ("binary_sensor.irrigation_bss_rain_blocked",
         "on" if machine_state in ("rain_blocked", "rain_today_blocked") else "off", {
             "friendly_name": "Irrigation BSS — Rain Blocked",
             "device_class": "problem",
             "icon": "mdi:weather-rainy",
             "integration": INTEGRATION_TAG,
         }),
        ("binary_sensor.irrigation_bss_frost_blocked",
         "on" if machine_state == "frost_protection" else "off", {
             "friendly_name": "Irrigation BSS — Frost Protection Active",
             "device_class": "problem",
             "icon": "mdi:snowflake-alert",
             "integration": INTEGRATION_TAG,
         }),
    ]


def _build_zone_entities(
    active_zones: list[dict],
    all_zones: list[dict],
) -> list[tuple[str, str, dict]]:
    """Build per-zone binary_sensor entities."""
    entities: list[tuple[str, str, dict]] = []
    active_ids = {z["zone_id"] for z in active_zones}

    for zone_info in active_zones:
        zid = zone_info["zone_id"]
        entities.append((
            f"binary_sensor.irrigation_bss_zone_{zid}", "on", {
                "friendly_name": f"Irrigation BSS — {zone_info['zone_name']}",
                "device_class": "running",
                "icon": "mdi:sprinkler",
                "zone_id": zid,
                "remaining_sec": zone_info["remaining_sec"],
                "duration_min": zone_info["duration_min"],
                "integration": INTEGRATION_TAG,
            },
        ))

    for zone in all_zones:
        if zone["id"] not in active_ids:
            entities.append((
                f"binary_sensor.irrigation_bss_zone_{zone['id']}", "off", {
                    "friendly_name": f"Irrigation BSS — {zone['name']}",
                    "device_class": "running",
                    "icon": "mdi:sprinkler",
                    "zone_id": zone["id"],
                    "remaining_sec": 0,
                    "integration": INTEGRATION_TAG,
                },
            ))

    return entities


# ---------------------------------------------------------------------------
# Main publish cycle
# ---------------------------------------------------------------------------
async def publish_once(http_session: aiohttp.ClientSession) -> None:
    """Collect current state and push all entities to HA."""
    if not settings.ha_token:
        return

    # 1. Gather runtime state
    active_zones = irrigation.get_active_zones()
    any_watering = len(active_zones) > 0

    # 2. Gather DB data (in thread to avoid blocking asyncio)
    lang = await asyncio.to_thread(_get_language_sync)
    next_run, planned_zone_name, all_zones, skips = await asyncio.to_thread(_get_db_data_sync)

    skip = await check_sensors_blocking(
        skip_if_raining=skips["skip_if_raining"],
        skip_if_rained_today=skips["skip_if_rained_today"],
        skip_if_soil_wet=skips["skip_if_soil_wet"],
        skip_if_frost=skips["skip_if_frost"]
    )
    rain_blocked = skip in (SkipReason.rain,)
    frost_blocked = skip in (SkipReason.frost,)

    # 3. Resolve display state
    machine_state = _resolve_machine_state(
        active_zones, rain_blocked, frost_blocked, next_run
    )
    active_zone_name = active_zones[0]["zone_name"] if active_zones else None
    display_state = _get_display_state(machine_state, lang, active_zone_name, planned_zone_name)
    dynamic_icon = _icon(machine_state)

    # 4. Build entity list
    entities = _build_core_entities(
        active_zones, any_watering, machine_state, display_state,
        dynamic_icon, skip, next_run, lang,
    )
    entities.extend(_build_zone_entities(active_zones, all_zones))

    # 5. Push all entities concurrently
    await asyncio.gather(*[
        _push_state(http_session, eid, state, attrs)
        for eid, state, attrs in entities
    ])

    logger.debug(f"Published {len(entities)} entities to HA")


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
async def run_publisher() -> None:
    """Main publisher loop — runs until stop() is called."""
    global _running
    _running = True
    logger.info(f"HA publisher started (interval: {PUBLISH_INTERVAL}s)")

    async with aiohttp.ClientSession() as http_session:
        while _running:
            try:
                await publish_once(http_session)
            except Exception as e:
                logger.warning(f"HA publisher error: {e}")
            await asyncio.sleep(PUBLISH_INTERVAL)


def start() -> None:
    """Start the publisher as an asyncio task."""
    global _publisher_task
    if _publisher_task is not None and not _publisher_task.done():
        logger.warning("HA publisher is already running. Ignoring start request.")
        return
    _publisher_task = asyncio.create_task(run_publisher())


def stop() -> None:
    """Signal the publisher to stop."""
    global _running
    _running = False