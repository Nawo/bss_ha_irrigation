"""
HA Publisher — periodically pushes irrigation state to Home Assistant entities.

All constants and configuration are defined at the top of the file.
Translations are loaded from the shared frontend locale JSON files via i18n module.
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
from backend.services.i18n import t as translate
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

# Map machine_state -> (translation key, mdi icon)
STATE_CONFIG: dict[str, tuple[str, str]] = {
    "active":             ("status.active",           "mdi:sprinkler"),
    "rain_blocked":       ("status.rainBlocked",      "mdi:weather-rainy"),
    "rain_today_blocked": ("status.rainTodayBlocked",  "mdi:weather-rainy"),
    "frost_protection":   ("status.frostProtection",   "mdi:snowflake"),
    "inactive":           ("status.inactive",          "mdi:sprinkler-variant"),
}

INTEGRATION_TAG = "irrigation_bss"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
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


def _get_db_data_sync() -> tuple[Optional[str], list[dict]]:
    """Read next_run and all zones from DB (runs in thread)."""
    with Session(engine) as session:
        schedules = session.exec(
            select(Schedule).where(Schedule.enabled == True)
        ).all()
        runs = [
            run for s in schedules
            if (run := sched.get_next_run(s.id)) is not None
        ]
        next_run = min(runs) if runs else None

        all_zones = session.exec(select(Zone)).all()
        zones_data = [{"id": z.id, "name": z.name} for z in all_zones]

    return next_run, zones_data


async def _check_rained_today() -> bool:
    """Check if any sensor with skip_if_rained_today has detected historical rain."""
    with Session(engine) as session:
        sensors = session.exec(
            select(Sensor).where(
                Sensor.enabled == True,
                Sensor.skip_if_rained_today == True,
            )
        ).all()

    if not sensors:
        return False

    local_now = datetime.now().astimezone()
    local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    utc_midnight = local_midnight.astimezone(timezone.utc).replace(tzinfo=None)

    for sensor in sensors:
        state = ha_client.get_cached_state(sensor.entity_id)
        if not state:
            continue
        val = str(state.get("state", "")).strip().lower()

        if sensor.sensor_type == SensorType.rain:
            if val == "on":
                return True
            history = await ha_client.get_history(sensor.entity_id, utc_midnight)
            if any(str(h.get("state")).strip().lower() == "on" for h in history if h):
                return True

        elif sensor.sensor_type == SensorType.weather:
            if val in RAIN_WEATHER_STATES:
                return False  # Currently raining — not "rained today" specifically
            history = await ha_client.get_history(sensor.entity_id, utc_midnight)
            if any(
                str(h.get("state")).strip().lower() in RAIN_WEATHER_STATES
                for h in history if h
            ):
                return True

    return False


# ---------------------------------------------------------------------------
# State resolution
# ---------------------------------------------------------------------------
def _resolve_machine_state(
    active_zones: list[dict],
    rain_blocked: bool,
    frost_blocked: bool,
    rained_today: bool,
) -> str:
    """Determine the machine_state string from current conditions."""
    if active_zones:
        return "active"
    if rained_today:
        return "rain_today_blocked"
    if rain_blocked:
        return "rain_blocked"
    if frost_blocked:
        return "frost_protection"
    return "inactive"


def _get_display_state(machine_state: str, lang: str, active_zone_name: Optional[str] = None) -> str:
    """Resolve display label from translation files."""
    t_key, _ = STATE_CONFIG.get(machine_state, ("status.inactive", "mdi:sprinkler-variant"))
    label = translate(t_key, lang)
    if machine_state == "active" and active_zone_name:
        return f"{label} - {active_zone_name}"
    return label


def _get_icon(machine_state: str) -> str:
    """Resolve MDI icon for a machine state."""
    _, icon = STATE_CONFIG.get(machine_state, ("status.inactive", "mdi:sprinkler-variant"))
    return icon


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
    friendly_name = translate("status.friendlyName", lang)

    return [
        ("binary_sensor.irrigation_bss_watering", "on" if any_watering else "off", {
            "friendly_name": "Irrigation BSS — Watering Active",
            "device_class": "running",
            "icon": "mdi:sprinkler-variant",
            "integration": INTEGRATION_TAG,
        }),
        ("sensor.irrigation_bss_watering_status", display_state, {
            "friendly_name": friendly_name,
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

    skip = await check_sensors_blocking()
    rain_blocked = skip in (SkipReason.rain,)
    frost_blocked = skip in (SkipReason.frost,)

    rained_today = False
    if rain_blocked:
        rained_today = await _check_rained_today()

    # 2. Gather DB data (in thread to avoid blocking asyncio)
    lang = await asyncio.to_thread(_get_language_sync)
    next_run, all_zones = await asyncio.to_thread(_get_db_data_sync)

    # 3. Resolve display state
    machine_state = _resolve_machine_state(
        active_zones, rain_blocked, frost_blocked, rained_today,
    )
    active_zone_name = active_zones[0]["zone_name"] if active_zones else None
    display_state = _get_display_state(machine_state, lang, active_zone_name)
    dynamic_icon = _get_icon(machine_state)

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