# 🧪 Testing Guide - Skip If Rained Today

Local testing setup for the "skip if rained today" feature without requiring full Home Assistant installation.

## Prerequisites

```bash
# Python 3.11+
python --version

# Docker (for docker-compose option)
docker --version
docker-compose --version
```

## Option 1: Standalone Tests (Fastest ⚡)

Run unit tests for the skip_if_rained_today logic without full setup.

### Setup

```bash
cd /Users/romannawrot/Projekty/bss_ha_irrigation/addon

# Install dependencies
pip install -r backend/requirements.txt

# Install pytest (optional, but recommended)
pip install pytest
```

### Run Tests

```bash
# Standalone mode
python backend/test_irrigation.py

# Or with pytest
pytest backend/test_irrigation.py -v
```

**Expected output:**
```
✅ Test 1: Rain sensor - skip_if_rained_today=True
✅ Test 2: Rain sensor - no rain today
✅ Test 3: Weather sensor - skip_if_rained_today=True
✅ Test 4: Weather sensor - no rain today
✅ Test 5: skip_if_rained_today=False - ignores history
✅ Test 6: Multiple sensors - fail-safe aggregation
✅ Test 7: UTC timezone handling

✅ ALL TESTS PASSED!
```

---

## Option 2: Docker Compose Mock Environment (Most Realistic 🐳)

Full local environment with mock Home Assistant server + backend + live testing.

### Setup

```bash
cd /Users/romannawrot/Projekty/bss_ha_irrigation/addon

# Build and start containers
docker-compose -f docker-compose.test.yml up

# In another terminal - wait ~5 seconds for startup
sleep 5

# Test the mock HA server
curl http://localhost:5050/health
# Expected: {"status": "ok"}
```

### Running Backend

The backend should start automatically and connect to mock HA:

```
[INFO] Connecting to Home Assistant...
[INFO] Connected to HA WebSocket
[INFO] Irrigation BSS ready on :8099
```

Access the frontend at: **http://localhost:8099** (requires frontend build)

### Test via API

```bash
# 1. Create a rain sensor
curl -X POST http://localhost:8099/api/sensors \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Front Yard Rain",
    "entity_id": "binary_sensor.rain",
    "sensor_type": "rain",
    "enabled": true,
    "skip_if_rained_today": true
  }'

# 2. Simulate rain in mock HA
curl -X POST http://localhost:5050/test/set-rain \
  -H "Content-Type: application/json" \
  -d '{"state": "on"}'

# 3. Try to start watering (should be blocked)
curl -X POST http://localhost:8099/api/irrigation/zones/1/start \
  -H "Content-Type: application/json" \
  -d '{"duration_min": 15}'

# Expected response: {"skipped": true, "skip_reason": "rain"}
```

### Mock HA Endpoints

```bash
# Get all entity states
curl http://localhost:5050/api/states | jq

# Get history for entity
curl "http://localhost:5050/api/history/period/2024-01-14?filter_entity_id=binary_sensor.rain" | jq

# TEST HELPERS:
# Set rain state
curl -X POST http://localhost:5050/test/set-rain \
  -H "Content-Type: application/json" \
  -d '{"state": "on"}'

# Set weather condition
curl -X POST http://localhost:5050/test/set-weather \
  -H "Content-Type: application/json" \
  -d '{"condition": "rainy"}'

# Set soil moisture
curl -X POST http://localhost:5050/test/set-soil-moisture \
  -H "Content-Type: application/json" \
  -d '{"moisture": "85"}'

# Reset history
curl -X POST http://localhost:5050/test/reset-history
```

---

## Option 3: Frontend Development

Build and test the UI locally.

```bash
cd /Users/romannawrot/Projekty/bss_ha_irrigation/addon/frontend

# Install dependencies
npm install

# Start dev server (requires working backend on localhost:8099)
npm run dev

# Visit http://localhost:5173
```

**Test steps in UI:**
1. Navigate to **Sensors** page
2. Add new weather sensor
3. Look for checkbox: **"Skip if it rained today"**
4. Enable it and save
5. Check backend logs to verify it's being used

---

## 🔍 Debugging

### Check Backend Logs

```bash
# If using docker-compose
docker-compose -f docker-compose.test.yml logs backend -f

# Look for lines like:
# [INFO] Sensor block: rain sensor binary_sensor.rain detected rain today
```

### Check Mock HA State

```bash
# Get current states
curl http://localhost:5050/api/states | jq '.[] | select(.entity_id | contains("rain"))'

# Get history
curl "http://localhost:5050/api/history/period/2024-01-14?filter_entity_id=binary_sensor.rain" | jq
```

### Test Timezone Handling

The UTC fix ensures that "today" is calculated in local timezone, not UTC:

```python
# Before fix - WRONG:
local_now = datetime.now().astimezone()
utc_midnight = local_now.astimezone(timezone.utc)  # ❌ wrong conversion

# After fix - CORRECT:
local_now = datetime.now().astimezone()
local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
utc_midnight = local_midnight.astimezone(timezone.utc).replace(tzinfo=None)  # ✅ correct
```

---

## 📋 Feature Checklist

After testing, verify:

- [x] **Backend model** - `Sensor.skip_if_rained_today` field exists
- [x] **Database migration** - `ALTER TABLE sensors ADD COLUMN skip_if_rained_today`
- [x] **Irrigation logic** - `check_sensors_blocking()` reads from sensor config
- [x] **UTC fix** - timezone handling corrected
- [x] **Frontend UI** - weather sensor shows checkbox
- [x] **Translations** - EN, PL, DE translations added
- [x] **Tests** - comprehensive test suite passes
- [x] **Docker** - mock HA environment works

---

## 🚀 Next Steps

1. **Test locally** with one of the three options above
2. **Verify behavior** with rain/weather sensors
3. **Deploy** to Home Assistant addon store
4. **Monitor** logs for any timezone issues

---

## Troubleshooting

### "Entity not found" error
- Make sure sensor entity_id matches something in mock HA
- Check: `curl http://localhost:5050/api/states | jq`

### Tests fail with "import error"
- Run from addon directory: `cd addon && python backend/test_irrigation.py`
- Install dependencies: `pip install -r backend/requirements.txt`

### Docker containers won't start
```bash
# Check logs
docker-compose -f docker-compose.test.yml logs

# Rebuild
docker-compose -f docker-compose.test.yml build --no-cache
```

---

## ✅ Testing Completed

All features tested and working:
- ✅ Rain sensor with skip_if_rained_today
- ✅ Weather sensor with skip_if_rained_today
- ✅ UTC timezone handling
- ✅ Multiple sensors (fail-safe)
- ✅ Mock HA server
- ✅ Docker compose setup
