import asyncio
import logging
from typing import Optional

import aiohttp
from sqlmodel import Session, select

from backend.config import settings
from backend.services import irrigation
from backend.services import scheduler as sched
from backend.database.db import engine
from backend.models import Schedule, Zone, AppSetting, SkipReason
from backend.services.irrigation import check_sensors_blocking

logger = logging.getLogger(__name__)

_running = False
_publisher_task: Optional[asyncio.Task] = None
PUBLISH_INTERVAL = 10

STATUS_LABELS = {
    "en": {
        "active": "Active",
        "rain_blocked": "Blocked - rain",
        "frost_protection": "Blocked - frost",
        "inactive": "Inactive",
        "friendly_name": "Irrigation BSS — Watering Status",
    },
    "pl": {
        "active": "Aktywne",
        "rain_blocked": "Zablokowane - deszcz",
        "frost_protection": "Zablokowane - mróz",
        "inactive": "Nieaktywne",
        "friendly_name": "Irrigation BSS — Status podlewania",
    },
}

async def _push_state(session: aiohttp.ClientSession, entity_id: str,
                      state: str, attributes: dict):
    url = f"{settings.ha_url}/api/states/{entity_id}"
    headers = {
        "Authorization": f"Bearer {settings.ha_token}",
        "Content-Type": "application/json",
    }
    payload = {"state": state, "attributes": attributes}
    try:
        async with session.post(url, json=payload, headers=headers,
                                timeout=aiohttp.ClientTimeout(total=5)) as resp:
            if resp.status not in (200, 201):
                logger.warning(f"HA push failed for {entity_id}: HTTP {resp.status}")
    except Exception as e:
        logger.debug(f"HA push error for {entity_id}: {e}")

def _get_language_sync() -> str:
    lang = settings.default_language
    try:
        with Session(engine) as session:
            row = session.get(AppSetting, "app_language")
            if row and row.value:
                lang = row.value
    except Exception:
        pass
    return lang

def _get_db_data_sync():
    """Wydzielona funkcja synchroniczna dla zapytań SQLModel"""
    with Session(engine) as session:
        schedules = session.exec(select(Schedule).where(Schedule.enabled == True)).all()
        runs = [sched.get_next_run(s.id) for s in schedules if sched.get_next_run(s.id)]
        next_run = min(runs) if runs else None
        all_zones = session.exec(select(Zone)).all()
        return next_run, all_zones

def _get_watering_state(active_zones: list[dict], rain_blocked: bool,
                        frost_blocked: bool, lang: str) -> tuple[str, str, str]:
    if active_zones:
        machine_state = "active"
        icon = "mdi:sprinkler"
    elif rain_blocked:
        machine_state = "rain_blocked"
        icon = "mdi:weather-rainy"
    elif frost_blocked:
        machine_state = "frost_protection"
        icon = "mdi:snowflake"
    else:
        machine_state = "inactive"
        icon = "mdi:sprinkler-variant"

    labels = STATUS_LABELS.get(lang, STATUS_LABELS["en"])
    active_zone_name = active_zones[0]["zone_name"] if active_zones else None
    
    if machine_state == "active" and active_zone_name:
        display_state = f"{labels['active']} - {active_zone_name}"
    else:
        display_state = labels[machine_state]
        
    return machine_state, display_state, icon

async def publish_once(http_session: aiohttp.ClientSession):
    if not settings.ha_token:
        return

    active_zones = irrigation.get_active_zones()
    any_watering = len(active_zones) > 0

    skip = await check_sensors_blocking()
    rain_blocked = skip in (SkipReason.rain,)
    frost_blocked = skip in (SkipReason.frost,)

    # Uruchomienie synchronicznych zapytań do DB w bezpiecznym wątku (zapobiega blokowaniu asyncio)
    lang = await asyncio.to_thread(_get_language_sync)
    next_run, all_zones = await asyncio.to_thread(_get_db_data_sync)

    active_zone = active_zones[0] if active_zones else None
    machine_state, display_state, dynamic_icon = _get_watering_state(
        active_zones, rain_blocked, frost_blocked, lang
    )

    entities = [
        ("binary_sensor.irrigation_bss_watering", "on" if any_watering else "off", {
            "friendly_name": "Irrigation BSS — Watering Active",
            "device_class": "running",
            "icon": "mdi:sprinkler-variant",
            "integration": "irrigation_bss",
        }),
        ("sensor.irrigation_bss_watering_status", display_state,
         {
             "friendly_name": STATUS_LABELS.get(lang, STATUS_LABELS["en"])["friendly_name"],
             "icon": dynamic_icon, # Dynamiczna ikona zdefiniowana wyżej
             "integration": "irrigation_bss",
             "status_reason": skip.value if skip else None,
             "state_value": machine_state,
             "active": any_watering,
             "active_zone": active_zone["zone_name"] if active_zone else None,
             "remaining_sec": active_zone["remaining_sec"] if active_zone else 0,
             "next_run": next_run or None,
             "status_text": display_state,
         }),
        ("sensor.irrigation_bss_active_zone", active_zone["zone_name"] if active_zone else "idle", {
            "friendly_name": "Irrigation BSS — Active Zone",
            "icon": "mdi:layers",
            "integration": "irrigation_bss",
        }),
        ("sensor.irrigation_bss_remaining_sec",
         str(active_zone["remaining_sec"]) if active_zone else "0", {
             "friendly_name": "Irrigation BSS — Remaining Time",
             "unit_of_measurement": "s",
             "icon": "mdi:timer-outline",
             "integration": "irrigation_bss",
         }),
        ("sensor.irrigation_bss_next_watering", next_run or "unknown", {
            "friendly_name": "Irrigation BSS — Next Watering",
            "device_class": "timestamp",
            "icon": "mdi:calendar-clock",
            "integration": "irrigation_bss",
        }),
        
        # ZMIANA: Klasa "problem" zapewni czerwoną ikonę natywnie w HA
        ("binary_sensor.irrigation_bss_rain_blocked", "on" if rain_blocked else "off", {
            "friendly_name": "Irrigation BSS — Rain Blocked",
            "device_class": "problem", 
            "icon": "mdi:weather-rainy",
            "integration": "irrigation_bss",
        }),
        ("binary_sensor.irrigation_bss_frost_blocked", "on" if frost_blocked else "off", {
            "friendly_name": "Irrigation BSS — Frost Protection Active",
            "device_class": "problem",
            "icon": "mdi:snowflake-alert",
            "integration": "irrigation_bss",
        }),
    ]

    for zone_info in active_zones:
        zid = zone_info["zone_id"]
        zname = zone_info["zone_name"]
        entities.append((
            f"binary_sensor.irrigation_bss_zone_{zid}",
            "on",
            {
                "friendly_name": f"Irrigation BSS — {zname}",
                "device_class": "running",
                "icon": "mdi:sprinkler",
                "zone_id": zid,
                "remaining_sec": zone_info["remaining_sec"],
                "duration_min": zone_info["duration_min"],
                "integration": "irrigation_bss",
            }
        ))

    active_ids = {z["zone_id"] for z in active_zones}
    for zone in all_zones:
        if zone.id not in active_ids:
            entities.append((
                f"binary_sensor.irrigation_bss_zone_{zone.id}",
                "off",
                {
                    "friendly_name": f"Irrigation BSS — {zone.name}",
                    "device_class": "running",
                    "icon": "mdi:sprinkler",
                    "zone_id": zone.id,
                    "remaining_sec": 0,
                    "integration": "irrigation_bss",
                }
            ))

    # Bezpieczne, jednoczesne wysyłanie żądań
    await asyncio.gather(*[
        _push_state(http_session, eid, state, attrs)
        for eid, state, attrs in entities
    ])

    logger.debug(f"Published {len(entities)} entities to HA")

async def run_publisher():
    global _running
    _running = True
    logger.info(f"HA publisher started (interval: {PUBLISH_INTERVAL}s)")
    
    # Utworzenie JEDNEJ sesji na cały cykl życia pętli
    async with aiohttp.ClientSession() as http_session:
        while _running:
            try:
                await publish_once(http_session)
            except Exception as e:
                logger.warning(f"HA publisher error: {e}")
            await asyncio.sleep(PUBLISH_INTERVAL)

def start():
    global _publisher_task
    # Zabezpieczenie przed Race Condition: jeśli task już istnieje i działa, nie odpalaj drugiego
    if _publisher_task is not None and not _publisher_task.done():
        logger.warning("HA publisher is already running. Ignoring start request.")
        return
        
    _publisher_task = asyncio.create_task(run_publisher())

def stop():
    global _running
    _running = False