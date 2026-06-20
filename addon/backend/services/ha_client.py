import asyncio
import json
import logging
from typing import Any, Callable, Dict, List, Optional
import aiohttp

from backend.config import settings

logger = logging.getLogger(__name__)

_ws: Optional[aiohttp.ClientWebSocketResponse] = None
_session: Optional[aiohttp.ClientSession] = None
_msg_id = 0
_pending: Dict[int, asyncio.Future] = {}
_state_listeners: List[Callable] = []
_states: Dict[str, Any] = {}
_is_connected: bool = False

MOCK_ENTITIES = [
    {"entity_id": "switch.valve_1", "state": "off", "attributes": {"friendly_name": "Wirtualny Zawór 1"}},
    {"entity_id": "switch.valve_2", "state": "off", "attributes": {"friendly_name": "Wirtualny Zawór 2"}},
    {"entity_id": "switch.valve_3", "state": "off", "attributes": {"friendly_name": "Wirtualny Zawór 3"}},
    {"entity_id": "binary_sensor.rain", "state": "off", "attributes": {"friendly_name": "Wirtualny Czujnik Deszczu", "device_class": "moisture"}},
    {"entity_id": "sensor.temp_front", "state": "25.0", "attributes": {"friendly_name": "Wirtualny Czujnik Temperatury", "unit_of_measurement": "°C", "device_class": "temperature"}},
    {"entity_id": "weather.forecast_dom", "state": "sunny", "attributes": {"friendly_name": "Wirtualna Pogoda Dom", "temperature": 25.0, "humidity": 45}},
    {"entity_id": "zone.home", "state": "zoning", "attributes": {"latitude": 52.2297, "longitude": 21.0122, "friendly_name": "Wirtualny Dom"}},
]


def _next_id() -> int:
    global _msg_id
    _msg_id += 1
    return _msg_id


def is_connected() -> bool:
    return _is_connected and _ws is not None and not _ws.closed


async def connect():
    global _ws, _session, _is_connected
    if settings.mock_ha:
        _is_connected = True
        for ent in MOCK_ENTITIES:
            _states[ent["entity_id"]] = ent
        logger.info("Connected to MOCKED HA (Local testing mode)")
        return

    _is_connected = False
    if _session and not _session.closed:
        try:
            await _session.close()
        except Exception:
            pass
    _session = aiohttp.ClientSession()
    ws_url = settings.ha_url.replace("http", "ws") + "/api/websocket"
    _ws = await _session.ws_connect(ws_url)
    asyncio.create_task(_receive_loop())
    logger.info("Connected to HA WebSocket")


async def _receive_loop():
    global _is_connected
    try:
        async for msg in _ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                await _handle_message(data)
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                logger.warning("HA WebSocket closed/error")
                break
    except Exception as e:
        logger.warning(f"HA WebSocket receive error: {e}")
    finally:
        _is_connected = False
        _cancel_pending()

    # Reconnect loop — retry until successful
    while True:
        logger.warning("HA WebSocket disconnected, reconnecting in 5s...")
        await asyncio.sleep(5)
        try:
            await connect()
            return
        except Exception as e:
            logger.warning(f"HA WebSocket reconnect failed: {e}, retrying...")


def _cancel_pending():
    for fut in list(_pending.values()):
        if not fut.done():
            fut.cancel()
    _pending.clear()


async def _handle_message(data: dict):
    global _is_connected
    msg_type = data.get("type")

    if msg_type == "auth_required":
        await _ws.send_json({"type": "auth", "access_token": settings.ha_token})

    elif msg_type == "auth_ok":
        logger.info("HA auth OK — subscribing to state changes")
        _is_connected = True
        await _subscribe_states()

    elif msg_type == "auth_invalid":
        logger.error("HA auth FAILED — check ha_token in config")

    elif msg_type == "result":
        msg_id = data.get("id")
        if msg_id in _pending:
            _pending[msg_id].set_result(data)
            del _pending[msg_id]

    elif msg_type == "event":
        event = data.get("event", {})
        if event.get("event_type") == "state_changed":
            ed = event.get("data", {})
            entity_id = ed.get("entity_id")
            new_state = ed.get("new_state")
            if entity_id and new_state:
                _states[entity_id] = new_state
                for listener in _state_listeners:
                    asyncio.create_task(listener(entity_id, new_state))


async def _subscribe_states():
    msg_id = _next_id()
    await _ws.send_json({
        "id": msg_id,
        "type": "subscribe_events",
        "event_type": "state_changed"
    })


async def _send(payload: dict) -> dict:
    if not is_connected():
        raise RuntimeError("Not connected to Home Assistant WebSocket")
    msg_id = _next_id()
    payload["id"] = msg_id
    loop = asyncio.get_event_loop()
    future = loop.create_future()
    _pending[msg_id] = future
    try:
        await _ws.send_json(payload)
    except Exception as e:
        _pending.pop(msg_id, None)
        if not future.done():
            future.cancel()
        raise RuntimeError(f"Cannot send to Home Assistant: {e}") from e
    return await asyncio.wait_for(future, timeout=10.0)


async def get_states() -> List[dict]:
    if settings.mock_ha:
        return list(_states.values())
        
    url = f"{settings.ha_url}/api/states"
    headers = {"Authorization": f"Bearer {settings.ha_token}"}
    async with aiohttp.ClientSession() as s:
        async with s.get(url, headers=headers) as resp:
            data = await resp.json()
            for entity in data:
                _states[entity["entity_id"]] = entity
            return data


async def get_state(entity_id: str) -> Optional[dict]:
    if settings.mock_ha:
        return _states.get(entity_id)
        
    if entity_id in _states:
        return _states[entity_id]
    url = f"{settings.ha_url}/api/states/{entity_id}"
    headers = {"Authorization": f"Bearer {settings.ha_token}"}
    async with aiohttp.ClientSession() as s:
        async with s.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                _states[entity_id] = data
                return data
    return None


async def call_service(domain: str, service: str, data: dict = None) -> dict:
    if settings.mock_ha:
        entity_id = data.get("entity_id") if data else None
        if entity_id and entity_id in _states:
            if service == "turn_on":
                _states[entity_id]["state"] = "on"
            elif service == "turn_off":
                _states[entity_id]["state"] = "off"
            elif service == "toggle":
                _states[entity_id]["state"] = "on" if _states[entity_id]["state"] == "off" else "off"
            
            for listener in _state_listeners:
                asyncio.create_task(listener(entity_id, _states[entity_id]["state"]))
        return {"success": True}

    return await _send({
        "type": "call_service",
        "domain": domain,
        "service": service,
        "service_data": data or {}
    })


async def call_service_with_response(domain: str, service: str, data: dict = None,
                                      target: dict = None) -> Optional[dict]:
    """Call an HA service that returns data (return_response=True)."""
    if settings.mock_ha:
        if domain == "weather" and service == "get_forecasts":
            entity_id = target.get("entity_id") if target else None
            from datetime import datetime, timedelta
            now = datetime.now()
            return {
                entity_id: {
                    "forecast": [
                        {"datetime": (now + timedelta(hours=1)).isoformat(), "condition": "sunny", "temperature": 26, "precipitation_probability": 0},
                        {"datetime": (now + timedelta(hours=2)).isoformat(), "condition": "partlycloudy", "temperature": 27, "precipitation_probability": 10},
                        {"datetime": (now + timedelta(hours=3)).isoformat(), "condition": "rainy", "temperature": 25, "precipitation_probability": 80},
                    ]
                }
            }
        return {}

    payload = {
        "type": "call_service",
        "domain": domain,
        "service": service,
        "service_data": data or {},
        "return_response": True,
    }
    if target:
        payload["target"] = target
    try:
        result = await _send(payload)
        if result.get("success"):
            return result.get("result", {}).get("response")
        logger.warning(f"call_service_with_response failed: {result}")
    except Exception as e:
        logger.warning(f"call_service_with_response error: {e}")
    return None


async def turn_on(entity_id: str):
    domain = entity_id.split(".")[0]
    await call_service(domain, "turn_on", {"entity_id": entity_id})
    logger.info(f"Turned ON: {entity_id}")


async def turn_off(entity_id: str):
    domain = entity_id.split(".")[0]
    await call_service(domain, "turn_off", {"entity_id": entity_id})
    logger.info(f"Turned OFF: {entity_id}")


def add_state_listener(callback: Callable):
    _state_listeners.append(callback)


def get_cached_state(entity_id: str) -> Optional[dict]:
    return _states.get(entity_id)


async def get_history(entity_id: str, start_time: "datetime") -> List[dict]:
    if settings.mock_ha:
        return []

    if not settings.ha_token:
        return []
    # start_time is timezone-aware UTC datetime
    iso_start = start_time.isoformat().replace("+00:00", "Z")
    url = f"{settings.ha_url}/api/history/period/{iso_start}?filter_entity_id={entity_id}"
    headers = {"Authorization": f"Bearer {settings.ha_token}"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10.0)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data and isinstance(data, list) and len(data) > 0:
                        return data[0]
    except Exception as e:
        logger.warning(f"Failed to fetch HA history for {entity_id}: {e}")
    return []
