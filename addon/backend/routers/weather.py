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
    from backend.services.weather import get_smart_scale
    scale = await get_smart_scale()
    return {"scale": scale}
