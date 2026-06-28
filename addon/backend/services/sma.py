import logging
from typing import List
from sqlmodel import Session, select
from backend.models.zone import Zone
from backend.models.sensor import Sensor, SensorType
from backend.services.weather import get_et0_and_precip
from backend.database.db import get_session, engine

logger = logging.getLogger(__name__)

# --- AGRONOMIC CONSTANTS ---
# Crop Coefficient (Kc)
KC_MAP = {
    "grass": 0.8,
    "shrubs": 0.5,
    "trees": 0.7,
    "vegetables": 1.0,
    "flowers": 0.6
}

# Root Depth (Zr) in meters
ZR_MAP = {
    "grass": 0.15,
    "shrubs": 0.40,
    "trees": 0.60,
    "vegetables": 0.30,
    "flowers": 0.20
}

# Available Water Capacity (AWC) in mm of water per 1 meter of soil depth
AWC_MAP = {
    "sand": 80.0,
    "loam": 150.0,
    "clay": 200.0,
    "universal": 150.0
}

# Irrigation Efficiency (IE)
EFFICIENCY_MAP = {
    "drip": 0.90,
    "rotor": 0.75,
    "spray": 0.65
}

# Sun Exposure modifier
EXPOSURE_MAP = {
    "full": 1.0,
    "partial": 0.8,
    "shade": 0.6
}


def get_zone_capacity_mm(zone: Zone) -> float:
    """Calculate the maximum water holding capacity of the root zone in mm."""
    awc = AWC_MAP.get(zone.soil_type, 150.0)
    zr = ZR_MAP.get(zone.plant_type, 0.15)
    return awc * zr


def get_zone_efficiency(zone: Zone) -> float:
    return EFFICIENCY_MAP.get(zone.emitter_type, 0.75)


def calculate_effective_precipitation(total_precip_mm: float) -> float:
    """Simple effective precipitation: if rain < 5mm it mostly evaporates. Above 5mm, 80% is effective."""
    if total_precip_mm < 5.0:
        return 0.0
    return total_precip_mm * 0.8


async def run_daily_sma_update() -> None:
    """
    Runs daily at midnight.
    Updates the water balance (depletion) for all zones based on yesterday's ET0, rain, and soil sensors.
    """
    logger.info("Running daily Soil Moisture Accounting (SMA) update...")

    # 1. Get yesterday's ET0 and precipitation
    weather_data = await get_et0_and_precip()
    # Actually, we should make sure get_et0_and_precip can return yesterday's history. 
    # For now, we will just use the current fetched data (which includes history if available).
    
    et0 = weather_data.get("et0_history", [0.0])[-1] if weather_data.get("et0_history") else 0.0
    precip = weather_data.get("precip_history", [0.0])[-1] if weather_data.get("precip_history") else 0.0
    
    effective_precip = calculate_effective_precipitation(precip)
    
    logger.info(f"SMA Data: ET0={et0}mm, Rain={precip}mm (Effective={effective_precip}mm)")

    with Session(engine) as session:
        zones = session.exec(select(Zone).where(Zone.enabled == True)).all()
        
        # Get all soil moisture sensors that are linked to zones
        soil_sensors = session.exec(
            select(Sensor)
            .where(Sensor.enabled == True)
            .where(Sensor.sensor_type == SensorType.soil)
            .where(Sensor.zone_id != None)
        ).all()
        
        # Build map for fast lookup
        zone_to_soil_sensor = {s.zone_id: s for s in soil_sensors}

        for zone in zones:
            max_capacity_mm = get_zone_capacity_mm(zone)
            
            # --- OVERRIDE FROM PHYSICAL SENSOR ---
            sensor = zone_to_soil_sensor.get(zone.id)
            if sensor:
                from backend.services import ha_client
                state = ha_client.get_cached_state(sensor.entity_id)
                ha_state = state.get("state") if state else "unavailable"
                
                if ha_state and ha_state not in ("unavailable", "unknown", "none"):
                    try:
                        # HA State for soil sensor should be in % (0-100)
                        moisture_percent = float(ha_state)
                        moisture_fraction = max(0.0, min(100.0, moisture_percent)) / 100.0
                        
                        # Depletion = max capacity - current water
                        new_depletion = max_capacity_mm * (1.0 - moisture_fraction)
                        logger.info(f"Zone {zone.name}: Sensor override to {moisture_percent}%. Depletion set to {new_depletion:.2f}mm")
                        zone.current_depletion_mm = new_depletion
                        continue # Skip mathematical model for this zone!
                    except ValueError:
                        logger.warning(f"Zone {zone.name}: Invalid HA state '{ha_state}' for sensor {sensor.name}. Falling back to mathematical model.")
                else:
                    logger.info(f"Zone {zone.name}: Soil sensor {sensor.name} is {ha_state}. Falling back to mathematical model.")

            # --- MATHEMATICAL MODEL (FAO-56 style) ---
            # Crop Evapotranspiration (ETc) = ET0 * Kc * Exposure
            kc = KC_MAP.get(zone.plant_type, 0.8)
            exposure = EXPOSURE_MAP.get(zone.sun_exposure, 1.0)
            etc = et0 * kc * exposure
            
            # New balance
            old_depletion = zone.current_depletion_mm
            new_depletion = old_depletion + etc - effective_precip
            
            # Bound the depletion between 0 (fully saturated) and max_capacity_mm (bone dry)
            new_depletion = max(0.0, min(max_capacity_mm, new_depletion))
            
            logger.info(f"Zone {zone.name}: Old Depletion: {old_depletion:.2f}mm -> ETc: {etc:.2f}mm -> Rain: {effective_precip:.2f}mm -> New Depletion: {new_depletion:.2f}mm (Max: {max_capacity_mm:.2f}mm)")
            zone.current_depletion_mm = new_depletion

        session.commit()
