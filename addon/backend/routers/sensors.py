from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from datetime import datetime, timezone

from backend.database.db import get_session
from backend.models import Sensor, SensorCreate, SensorUpdate, SensorRead, SensorType
from backend.constants import RAIN_WEATHER_STATES
from backend.services import ha_client
from backend.services.irrigation import _active

router = APIRouter(prefix="/api/sensors", tags=["sensors"])


async def _enrich(sensor: Sensor) -> SensorRead:
    sr = SensorRead.model_validate(sensor)
    state = ha_client.get_cached_state(sensor.entity_id)
    sr.ha_state = state.get("state") if state else "unavailable"

    # default
    sr.is_blocking = False
    sr.rained_today = None

    if state and sensor.enabled:
        val = state.get("state", "")
        if sensor.sensor_type == SensorType.rain:
            sr.is_blocking = val == "on"
            if sensor.skip_if_rained_today:
                # compute history since local midnight
                local_now = datetime.now().astimezone()
                local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
                utc_midnight = local_midnight.astimezone(timezone.utc).replace(tzinfo=None)
                history = await ha_client.get_history(sensor.entity_id, utc_midnight)
                sr.rained_today = val == "on" or any(str(h.get("state")).strip().lower() == "on" for h in history if h)
                if sr.rained_today:
                    sr.is_blocking = True
        elif sensor.sensor_type == SensorType.temperature:
            try:
                sr.is_blocking = float(val) < (sensor.threshold or 2.0)
            except (ValueError, TypeError):
                pass
        elif sensor.sensor_type == SensorType.soil:
            try:
                sr.is_blocking = float(val) > (sensor.threshold or 80.0)
            except (ValueError, TypeError):
                pass
        elif sensor.sensor_type == SensorType.flow:
            try:
                threshold = sensor.threshold if sensor.threshold is not None else 0.0
                sr.is_blocking = len(_active) == 0 and float(val) > threshold
            except (ValueError, TypeError):
                pass
    return sr


@router.get("", response_model=List[SensorRead])
async def list_sensors(session: Session = Depends(get_session)):
    sensors = session.exec(select(Sensor)).all()
    result = []
    for s in sensors:
        result.append(await _enrich(s))
    return result


@router.post("", response_model=SensorRead, status_code=201)
async def create_sensor(sensor_in: SensorCreate, session: Session = Depends(get_session)):
    sensor = Sensor.model_validate(sensor_in)
    session.add(sensor)
    session.commit()
    session.refresh(sensor)
    return await _enrich(sensor)


@router.get("/{sensor_id}", response_model=SensorRead)
async def get_sensor(sensor_id: int, session: Session = Depends(get_session)):
    sensor = session.get(Sensor, sensor_id)
    if not sensor:
        raise HTTPException(404, "Sensor not found")
    return await _enrich(sensor)


@router.patch("/{sensor_id}", response_model=SensorRead)
async def update_sensor(sensor_id: int, sensor_in: SensorUpdate, session: Session = Depends(get_session)):
    sensor = session.get(Sensor, sensor_id)
    if not sensor:
        raise HTTPException(404, "Sensor not found")
    for key, val in sensor_in.model_dump(exclude_unset=True).items():
        setattr(sensor, key, val)
    session.add(sensor)
    session.commit()
    session.refresh(sensor)
    return await _enrich(sensor)


@router.delete("/{sensor_id}", status_code=204)
def delete_sensor(sensor_id: int, session: Session = Depends(get_session)):
    sensor = session.get(Sensor, sensor_id)
    if not sensor:
        raise HTTPException(404, "Sensor not found")
    session.delete(sensor)
    session.commit()
