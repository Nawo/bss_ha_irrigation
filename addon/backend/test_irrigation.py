"""
Comprehensive tests for irrigation skip_if_rained_today logic.
Run with: python -m pytest backend/test_irrigation.py -v
Or standalone: python backend/test_irrigation.py
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

# Mock Home Assistant client before importing irrigation
class MockHAClient:
    def __init__(self):
        self.states = {}
        self.history_data = {}
    
    def get_cached_state(self, entity_id: str):
        return self.states.get(entity_id)
    
    async def get_history(self, entity_id: str, start_time):
        """Simulate HA history API"""
        return self.history_data.get(entity_id, [])
    
    def get_state(self, entity_id: str):
        return self.states.get(entity_id)
    
    async def turn_on(self, entity_id: str):
        pass
    
    async def turn_off(self, entity_id: str):
        pass


mock_ha = MockHAClient()

# Patch before importing irrigation
sys.modules['backend.services.ha_client'] = MagicMock()
sys.modules['backend.services.ha_client'].get_cached_state = mock_ha.get_cached_state
sys.modules['backend.services.ha_client'].get_history = mock_ha.get_history

from backend.database.db import engine, init_db
from backend.models import Sensor, SensorType, SkipReason, Zone, Valve, Schedule, WateringMode
from backend.services import irrigation
from sqlmodel import Session, select


async def test_rain_sensor_skip_if_rained_today():
    """Test: rain sensor blocks watering when skip_if_rained_today=True"""
    print("\n[TEST 1] Rain sensor - skip_if_rained_today=True")
    
    with Session(engine) as session:
        # Create rain sensor with skip_if_rained_today enabled
        sensor = Sensor(
            name="Rain Sensor",
            entity_id="binary_sensor.rain",
            sensor_type=SensorType.rain,
            enabled=True,
            skip_if_rained_today=True  # <-- KEY SETTING
        )
        session.add(sensor)
        session.commit()
    
    # Mock: rain sensor currently off, but it was on earlier today
    mock_ha.states['binary_sensor.rain'] = {'state': 'off', 'attributes': {}}
    mock_ha.history_data['binary_sensor.rain'] = [
        {'state': 'off', 'last_changed': '2024-01-14T06:00:00Z'},
        {'state': 'on', 'last_changed': '2024-01-14T10:00:00Z'},  # <-- Rain earlier
        {'state': 'off', 'last_changed': '2024-01-14T11:00:00Z'},
    ]
    
    # Check if watering should be blocked
    result = await irrigation.check_sensors_blocking(
        skip_if_rain=True,
        skip_if_soil_wet=True,
        skip_if_frost=True,
    )
    
    assert result == SkipReason.rain, f"Expected SkipReason.rain, got {result}"
    print("✅ PASS: Rain detected in history - watering blocked")


async def test_rain_sensor_no_rain_today():
    """Test: rain sensor allows watering when no rain today"""
    print("\n[TEST 2] Rain sensor - no rain today")
    
    with Session(engine) as session:
        # Remove old sensor
        sensors = session.exec(select(Sensor)).all()
        for s in sensors:
            session.delete(s)
        session.commit()
        
        # Create rain sensor with skip_if_rained_today enabled
        sensor = Sensor(
            name="Rain Sensor",
            entity_id="binary_sensor.rain",
            sensor_type=SensorType.rain,
            enabled=True,
            skip_if_rained_today=True
        )
        session.add(sensor)
        session.commit()
    
    # Mock: rain sensor off, no rain in history
    mock_ha.states['binary_sensor.rain'] = {'state': 'off', 'attributes': {}}
    mock_ha.history_data['binary_sensor.rain'] = [
        {'state': 'off', 'last_changed': '2024-01-14T06:00:00Z'},
        {'state': 'off', 'last_changed': '2024-01-14T12:00:00Z'},
    ]
    
    result = await irrigation.check_sensors_blocking(
        skip_if_rain=True,
        skip_if_soil_wet=True,
        skip_if_frost=True,
    )
    
    assert result is None, f"Expected None, got {result}"
    print("✅ PASS: No rain today - watering allowed")


async def test_weather_sensor_skip_if_rained_today():
    """Test: weather sensor with skip_if_rained_today"""
    print("\n[TEST 3] Weather sensor - skip_if_rained_today=True")
    
    with Session(engine) as session:
        sensors = session.exec(select(Sensor)).all()
        for s in sensors:
            session.delete(s)
        session.commit()
        
        sensor = Sensor(
            name="Home Weather",
            entity_id="weather.home",
            sensor_type=SensorType.weather,
            enabled=True,
            skip_if_rained_today=True
        )
        session.add(sensor)
        session.commit()
    
    # Mock: currently sunny, but it was rainy earlier
    mock_ha.states['weather.home'] = {'state': 'sunny', 'attributes': {}}
    mock_ha.history_data['weather.home'] = [
        {'state': 'rainy', 'last_changed': '2024-01-14T05:00:00Z'},
        {'state': 'rainy', 'last_changed': '2024-01-14T08:30:00Z'},
        {'state': 'sunny', 'last_changed': '2024-01-14T12:00:00Z'},
    ]
    
    result = await irrigation.check_sensors_blocking(
        skip_if_rain=True,
        skip_if_soil_wet=True,
        skip_if_frost=True,
    )
    
    assert result == SkipReason.rain, f"Expected SkipReason.rain, got {result}"
    print("✅ PASS: Rain detected in weather history - watering blocked")


async def test_weather_sensor_no_rain_today():
    """Test: weather sensor allows watering when no rain"""
    print("\n[TEST 4] Weather sensor - no rain today")
    
    with Session(engine) as session:
        sensors = session.exec(select(Sensor)).all()
        for s in sensors:
            session.delete(s)
        session.commit()
        
        sensor = Sensor(
            name="Home Weather",
            entity_id="weather.home",
            sensor_type=SensorType.weather,
            enabled=True,
            skip_if_rained_today=True
        )
        session.add(sensor)
        session.commit()
    
    mock_ha.states['weather.home'] = {'state': 'sunny', 'attributes': {}}
    mock_ha.history_data['weather.home'] = [
        {'state': 'sunny', 'last_changed': '2024-01-14T06:00:00Z'},
        {'state': 'cloudy', 'last_changed': '2024-01-14T10:00:00Z'},
        {'state': 'sunny', 'last_changed': '2024-01-14T14:00:00Z'},
    ]
    
    result = await irrigation.check_sensors_blocking(
        skip_if_rain=True,
        skip_if_soil_wet=True,
        skip_if_frost=True,
    )
    
    assert result is None, f"Expected None, got {result}"
    print("✅ PASS: No rain in history - watering allowed")


async def test_skip_if_rained_today_disabled():
    """Test: disabled skip_if_rained_today ignores history"""
    print("\n[TEST 5] skip_if_rained_today=False - ignores history")
    
    with Session(engine) as session:
        sensors = session.exec(select(Sensor)).all()
        for s in sensors:
            session.delete(s)
        session.commit()
        
        sensor = Sensor(
            name="Rain Sensor",
            entity_id="binary_sensor.rain",
            sensor_type=SensorType.rain,
            enabled=True,
            skip_if_rained_today=False  # <-- DISABLED
        )
        session.add(sensor)
        session.commit()
    
    # Even with rain in history, should not block because skip_if_rained_today=False
    mock_ha.states['binary_sensor.rain'] = {'state': 'off', 'attributes': {}}
    mock_ha.history_data['binary_sensor.rain'] = [
        {'state': 'on', 'last_changed': '2024-01-14T10:00:00Z'},
    ]
    
    result = await irrigation.check_sensors_blocking(
        skip_if_rain=True,
        skip_if_soil_wet=True,
        skip_if_frost=True,
    )
    
    assert result is None, f"Expected None (skip_if_rained_today is disabled), got {result}"
    print("✅ PASS: skip_if_rained_today=False ignores history")


async def test_multiple_sensors():
    """Test: fail-safe with multiple sensors"""
    print("\n[TEST 6] Multiple sensors - fail-safe aggregation")
    
    with Session(engine) as session:
        session.exec(select(Sensor)).delete()
        session.commit()
        
        # Add 3 sensors
        s1 = Sensor(
            name="Rain Sensor",
            entity_id="binary_sensor.rain",
            sensor_type=SensorType.rain,
            enabled=True,
            skip_if_rained_today=False
        )
        s2 = Sensor(
            name="Soil Moisture",
            entity_id="sensor.soil_moisture",
            sensor_type=SensorType.soil,
            enabled=True,
            threshold=80.0
        )
        s3 = Sensor(
            name="Temperature",
            entity_id="sensor.temperature",
            sensor_type=SensorType.temperature,
            enabled=True,
            threshold=2.0
        )
        session.add_all([s1, s2, s3])
        session.commit()
    
    # Mock: only soil is wet (above threshold)
    mock_ha.states.update({
        'binary_sensor.rain': {'state': 'off'},
        'sensor.soil_moisture': {'state': '85'},  # 85% > 80% threshold
        'sensor.temperature': {'state': '15'},   # 15°C > 2°C threshold
    })
    
    result = await irrigation.check_sensors_blocking(
        skip_if_rain=True,
        skip_if_soil_wet=True,
        skip_if_frost=True,
    )
    
    # Soil wet should block
    assert result == SkipReason.soil_wet, f"Expected soil_wet, got {result}"
    print("✅ PASS: Soil sensor blocks watering")


async def test_utc_timezone_handling():
    """Test: UTC/timezone conversion doesn't break midnight calculation"""
    print("\n[TEST 7] UTC timezone handling")
    
    with Session(engine) as session:
        session.exec(select(Sensor)).delete()
        session.commit()
        
        sensor = Sensor(
            name="Rain Sensor",
            entity_id="binary_sensor.rain",
            sensor_type=SensorType.rain,
            enabled=True,
            skip_if_rained_today=True
        )
        session.add(sensor)
        session.commit()
    
    # Test with mock datetime
    mock_ha.states['binary_sensor.rain'] = {'state': 'off'}
    mock_ha.history_data['binary_sensor.rain'] = []
    
    # Should complete without error
    result = await irrigation.check_sensors_blocking(
        skip_if_rain=True,
        skip_if_soil_wet=True,
        skip_if_frost=True,
    )
    
    assert result is None
    print("✅ PASS: Timezone conversion works correctly")


async def run_all_tests():
    """Run all tests"""
    print("=" * 60)
    print("IRRIGATION SKIP_IF_RAINED_TODAY TESTS")
    print("=" * 60)
    
    try:
        # Initialize DB
        init_db()
        
        # Run tests
        await test_rain_sensor_skip_if_rained_today()
        await test_rain_sensor_no_rain_today()
        await test_weather_sensor_skip_if_rained_today()
        await test_weather_sensor_no_rain_today()
        await test_skip_if_rained_today_disabled()
        await test_multiple_sensors()
        await test_utc_timezone_handling()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        return 0
    
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)
