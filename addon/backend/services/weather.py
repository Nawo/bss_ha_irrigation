"""
Weather service — reads from HA weather entity or Open-Meteo API (free, no key needed).
"""
import logging
from typing import Optional
from datetime import datetime, timezone
import aiohttp

from backend.services import ha_client

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


async def get_forecast(weather_entity_id: Optional[str] = None,
                       lat: Optional[float] = None,
                       lon: Optional[float] = None) -> dict:
    """
    Returns: {
        condition: str,
        temperature: float,
        rain_expected_24h: bool,
        forecast: [...]
    }
    """
    if weather_entity_id:
        return await _from_ha_entity(weather_entity_id)
    if lat and lon:
        return await _from_open_meteo(lat, lon)
    return {"condition": "unknown", "temperature": None,
            "rain_expected_24h": False, "rain_detected_today": False, "forecast": []}


async def _from_ha_entity(entity_id: str) -> dict:
    state = ha_client.get_cached_state(entity_id)
    if not state:
        return {"condition": "unknown", "temperature": None,
                "rain_expected_24h": False, "rain_detected_today": False, "forecast": []}

    attrs = state.get("attributes", {})
    condition = state.get("state", "unknown")
    temp = attrs.get("temperature")
    rain_conditions = {"rainy", "pouring", "lightning-rainy", "lightning"}

    # Try to get forecast from attributes first (older HA versions)
    raw_forecast = attrs.get("forecast", [])

    # If forecast is empty, try the weather.get_forecasts service (HA 2024.3+)
    if not raw_forecast:
        try:
            response = await ha_client.call_service_with_response(
                "weather", "get_forecasts",
                data={"type": "hourly"},
                target={"entity_id": entity_id},
            )
            if response and entity_id in response:
                raw_forecast = response[entity_id].get("forecast", [])
        except Exception as e:
            logger.warning(f"Failed to get forecast from HA service: {e}")
            # Try daily forecast as fallback
            try:
                response = await ha_client.call_service_with_response(
                    "weather", "get_forecasts",
                    data={"type": "daily"},
                    target={"entity_id": entity_id},
                )
                if response and entity_id in response:
                    raw_forecast = response[entity_id].get("forecast", [])
            except Exception:
                pass

    forecast = []
    rain_in_forecast = False
    for f in raw_forecast[:24]:
        fc = f.get("condition", "unknown")
        if fc in rain_conditions:
            rain_in_forecast = True
        forecast.append({
            "datetime": f.get("datetime"),
            "condition": fc,
            "temperature": f.get("temperature"),
        })

    rain_expected = condition in rain_conditions or rain_in_forecast

    local_now = datetime.now().astimezone()
    local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    utc_midnight = local_midnight.astimezone(timezone.utc).replace(tzinfo=None)
    
    rain_detected = condition in rain_conditions
    if not rain_detected:
        history = await ha_client.get_history(entity_id, utc_midnight)
        if any(str(h.get("state")).strip().lower() in rain_conditions for h in history if h):
            rain_detected = True

    return {
        "condition": condition,
        "temperature": temp,
        "rain_expected_24h": rain_expected,
        "rain_detected_today": rain_detected,
        "forecast": forecast,
    }


async def _from_open_meteo(lat: float, lon: float) -> dict:
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,weathercode",
        "hourly": "temperature_2m,weathercode",
        "forecast_days": 1,
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(OPEN_METEO_URL, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()

        current = data.get("current", {})
        temp = current.get("temperature_2m")
        hourly_codes = data.get("hourly", {}).get("weathercode", [])
        hourly_temps = data.get("hourly", {}).get("temperature_2m", [])
        rain_codes = set(range(51, 68)) | set(range(80, 83)) | set(range(95, 100))
        
        rain_expected = any(c in rain_codes for c in hourly_codes)
        
        current_hour = datetime.now().astimezone().hour
        rain_detected = any(c in rain_codes for c in hourly_codes[:current_hour + 1])

        forecast = []
        hourly_time = data.get("hourly", {}).get("time", [])
        for i, code in enumerate(hourly_codes[:24]):
            forecast.append({
                "datetime": hourly_time[i] if i < len(hourly_time) else None,
                "condition": _wmo_to_condition(code),
                "temperature": hourly_temps[i] if i < len(hourly_temps) else None,
            })

        return {
            "condition": _wmo_to_condition(current.get("weathercode", 0)),
            "temperature": temp,
            "rain_expected_24h": rain_expected,
            "rain_detected_today": rain_detected,
            "forecast": forecast,
        }
    except Exception as e:
        logger.error(f"Open-Meteo fetch failed: {e}")
        return {"condition": "unknown", "temperature": None,
                "rain_expected_24h": False, "rain_detected_today": False, "forecast": []}


def _wmo_to_condition(code: int) -> str:
    if code == 0:
        return "sunny"
    if code in range(1, 4):
        return "partlycloudy"
    if code in range(51, 68) or code in range(80, 83):
        return "rainy"
    if code in range(71, 78) or code in range(85, 87):
        return "snowy"
    if code in range(95, 100):
        return "lightning-rainy"
    return "cloudy"
