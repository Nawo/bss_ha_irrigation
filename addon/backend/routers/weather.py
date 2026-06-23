from typing import Optional
from fastapi import APIRouter, Query

from backend.services.weather import get_forecast

router = APIRouter(prefix="/api/weather", tags=["weather"])


@router.get("")
async def weather(
    entity_id: Optional[str] = Query(None),
    lat: Optional[float] = Query(None),
    lon: Optional[float] = Query(None),
):
    return await get_forecast(weather_entity_id=entity_id, lat=lat, lon=lon)

@router.get("/et0")
async def weather_et0():
    from backend.services.weather import get_smart_scale, get_et0_data
    from sqlmodel import Session
    from backend.database.db import engine
    from backend.models import AppSetting

    lat = 52.2297
    lon = 21.0122
    try:
        with Session(engine) as session:
            lat_row = session.get(AppSetting, "weather_lat")
            lon_row = session.get(AppSetting, "weather_lon")
            if lat_row and lat_row.value:
                lat = float(lat_row.value)
            if lon_row and lon_row.value:
                lon = float(lon_row.value)
    except Exception:
        pass

    scale = await get_smart_scale()
    et_data = await get_et0_data(lat, lon)
    return {
        "scale": scale,
        "et0": et_data.get("et0", 0),
        "precipitation": et_data.get("precipitation", 0),
        "effective_demand": max(0, (et_data.get("et0", 0) or 0) - (et_data.get("precipitation", 0) or 0)),
        "lat": lat,
        "lon": lon,
    }
