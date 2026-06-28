from typing import Optional, List
from sqlmodel import SQLModel, Field


class ZoneBase(SQLModel):
    name: str = Field(min_length=1, max_length=100)
    color: str = Field(default="#22c55e", max_length=20)
    description: Optional[str] = Field(default=None, max_length=500)
    sequence_order: int = Field(default=0, ge=0)
    enabled: bool = Field(default=True)
    # Smart Watering 2.0 (SMA) parameters
    plant_type: str = Field(default="grass") # grass, shrubs, trees, vegetables
    emitter_type: str = Field(default="rotor") # drip, spray, rotor
    soil_type: str = Field(default="loam") # sand, loam, clay
    sun_exposure: str = Field(default="full") # full, partial, shade
    area_m2: float = Field(default=10.0, ge=0.1)
    flow_lpm: float = Field(default=10.0, ge=0.1)
    current_depletion_mm: float = Field(default=0.0, ge=0.0)


class Zone(ZoneBase, table=True):
    __tablename__ = "zones"
    id: Optional[int] = Field(default=None, primary_key=True)


class ZoneCreate(ZoneBase):
    pass


class ZoneUpdate(SQLModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    color: Optional[str] = Field(default=None, max_length=20)
    description: Optional[str] = None
    sequence_order: Optional[int] = Field(default=None, ge=0)
    enabled: Optional[bool] = None
    plant_type: Optional[str] = None
    emitter_type: Optional[str] = None
    soil_type: Optional[str] = None
    sun_exposure: Optional[str] = None
    area_m2: Optional[float] = Field(default=None, ge=0.1)
    flow_lpm: Optional[float] = Field(default=None, ge=0.1)
    current_depletion_mm: Optional[float] = Field(default=None, ge=0.0)


class ZoneRead(ZoneBase):
    id: int
    valve_count: int = 0
    is_watering: bool = False
