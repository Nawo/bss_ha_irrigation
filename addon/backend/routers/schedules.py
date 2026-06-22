from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from backend.database.db import get_session
from backend.models import Schedule, ScheduleCreate, ScheduleUpdate, ScheduleRead, Zone, schedule_zone_ids
from backend.services import scheduler as sched_service

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


async def _enrich(schedule: Schedule, session: Session) -> ScheduleRead:
    sr = ScheduleRead.model_validate(schedule)
    zone = session.get(Zone, schedule.zone_id)
    sr.zone_name = zone.name if zone else None
    sr.all_zone_ids = schedule_zone_ids(schedule)
    sr.next_run = sched_service.get_next_run(schedule.id)

    if sr.next_run:
        try:
            from datetime import datetime, timezone
            from backend.services.irrigation import check_sensors_blocking
            import logging

            logger = logging.getLogger(__name__)
            next_run_dt = datetime.fromisoformat(sr.next_run)
            local_now = datetime.now().astimezone()
            local_next_run = next_run_dt.astimezone(local_now.tzinfo)

            # If the scheduled run is today
            if local_next_run.date() == local_now.date():
                if schedule.force_next_run:
                    skip = None
                else:
                    skip = await check_sensors_blocking(
                        skip_if_raining=schedule.skip_if_raining,
                        skip_if_rained_today=schedule.skip_if_rained_today,
                        skip_if_soil_wet=schedule.skip_if_soil_wet,
                        skip_if_frost=schedule.skip_if_frost,
                    )
                if skip:
                    sr.next_run_will_be_skipped = True
                    sr.next_run_skipped_reason = skip.value
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Error checking next run skip status: {e}")

    return sr


@router.get("", response_model=List[ScheduleRead])
async def list_schedules(session: Session = Depends(get_session)):
    schedules = session.exec(select(Schedule)).all()
    enriched = []
    for s in schedules:
        enriched.append(await _enrich(s, session))
    return enriched


@router.post("", response_model=ScheduleRead, status_code=201)
async def create_schedule(schedule_in: ScheduleCreate, session: Session = Depends(get_session)):
    zone = session.get(Zone, schedule_in.zone_id)
    if not zone:
        raise HTTPException(404, "Zone not found")
    schedule = Schedule.model_validate(schedule_in)
    session.add(schedule)
    session.commit()
    session.refresh(schedule)
    sched_service.reload_schedules()
    return await _enrich(schedule, session)


@router.get("/{schedule_id}", response_model=ScheduleRead)
async def get_schedule(schedule_id: int, session: Session = Depends(get_session)):
    schedule = session.get(Schedule, schedule_id)
    if not schedule:
        raise HTTPException(404, "Schedule not found")
    return await _enrich(schedule, session)


@router.patch("/{schedule_id}", response_model=ScheduleRead)
async def update_schedule(schedule_id: int, schedule_in: ScheduleUpdate,
                    session: Session = Depends(get_session)):
    schedule = session.get(Schedule, schedule_id)
    if not schedule:
        raise HTTPException(404, "Schedule not found")
    for key, val in schedule_in.model_dump(exclude_unset=True).items():
        setattr(schedule, key, val)
    session.add(schedule)
    session.commit()
    session.refresh(schedule)
    sched_service.reload_schedules()
    return await _enrich(schedule, session)


@router.delete("/{schedule_id}", status_code=204)
async def delete_schedule(schedule_id: int, session: Session = Depends(get_session)):
    schedule = session.get(Schedule, schedule_id)
    if not schedule:
        raise HTTPException(404, "Schedule not found")
    session.delete(schedule)
    session.commit()
    sched_service.reload_schedules()
