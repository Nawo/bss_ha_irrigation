from typing import Optional, List
from sqlmodel import SQLModel, Field


class ZoneBase(SQLModel):
    name: str = Field(min_length=1, max_length=100)
    color: str = Field(default="#22c55e", max_length=20)
    description: Optional[str] = Field(default=None, max_length=500)
    duration_min: int = Field(default=15, ge=1, le=240)
    sequence_order: int = Field(default=0, ge=0)
    enabled: bool = Field(default=True)
    area_m2: Optional[float] = Field(default=None, ge=0.1)
    flow_lpm: Optional[float] = Field(default=None, ge=0.1)
    soil_type: Optional[str] = Field(default=None, max_length=20)
    sun_exposure: Optional[str] = Field(default=None, max_length=20)


class Zone(ZoneBase, table=True):
    __tablename__ = "zones"
    id: Optional[int] = Field(default=None, primary_key=True)


class ZoneCreate(ZoneBase):
    pass


class ZoneUpdate(SQLModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    color: Optional[str] = Field(default=None, max_length=20)
    description: Optional[str] = None
    duration_min: Optional[int] = Field(default=None, ge=1, le=240)
    sequence_order: Optional[int] = Field(default=None, ge=0)
    enabled: Optional[bool] = None
    area_m2: Optional[float] = Field(default=None, ge=0.1)
    flow_lpm: Optional[float] = Field(default=None, ge=0.1)
    soil_type: Optional[str] = Field(default=None, max_length=20)
    sun_exposure: Optional[str] = Field(default=None, max_length=20)


class ZoneRead(ZoneBase):
    id: int
    valve_count: int = 0
    is_watering: bool = False
