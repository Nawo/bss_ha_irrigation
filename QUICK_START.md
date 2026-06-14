# 🚀 Quick Start - Skip If Rained Today Feature

## What Changed?

✅ **Feature moved from Schedule → Sensor**
- The "skip if it rained today" checkbox is now per-weather-sensor, not per-schedule
- When watering is triggered, it checks if ANY weather sensor has this enabled
- If yes, checks history: did it rain today? If yes → blocks watering

✅ **UTC Timezone Bug Fixed**
- Old code broke "today" calculation in non-UTC timezones
- Fixed: now correctly handles Poland, Germany, etc.

✅ **UI Updated**
- Sensors page now shows checkbox for weather sensors
- Works in English, Polish, German

---

## Testing Locally (Pick One)

### 🟢 **Option 1: Quick Unit Tests** (2 min, no Docker needed)

```bash
cd /Users/romannawrot/Projekty/bss_ha_irrigation/addon

# Create virtual environment
bash setup_test_env.sh

# Activate it
source .venv/bin/activate

# Run tests
python backend/test_irrigation.py

# Expected output:
# ✅ Test 1: Rain sensor - skip_if_rained_today=True
# ✅ Test 2: Rain sensor - no rain today
# ... (7 tests total)
# ✅ ALL TESTS PASSED!
```

---

### 🔵 **Option 2: Full Local Environment** (5 min, needs Docker)

```bash
cd /Users/romannawrot/Projekty/bss_ha_irrigation/addon

# Start containers (mock HA + backend)
docker-compose -f docker-compose.test.yml up

# In another terminal, test the API:
curl http://localhost:5050/health
# Response: {"status":"ok"}

# Create a weather sensor:
curl -X POST http://localhost:8099/api/sensors \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Home Weather",
    "entity_id": "weather.home",
    "sensor_type": "weather",
    "enabled": true,
    "skip_if_rained_today": true
  }'

# Simulate rain
curl -X POST http://localhost:5050/test/set-weather \
  -H "Content-Type: application/json" \
  -d '{"condition": "rainy"}'

# Try to water (should be blocked)
curl http://localhost:8099/api/irrigation/zones/1/start
# Response: {"skipped": true, "skip_reason": "rain"}
```

---

### 🟣 **Option 3: Frontend Dev** (needs running backend)

```bash
cd /Users/romannawrot/Projekty/bss_ha_irrigation/addon/frontend

npm install
npm run dev
# Visit http://localhost:5173

# Steps:
# 1. Go to Sensors page
# 2. Add a weather sensor
# 3. Look for checkbox: "Skip if it rained today"
# 4. Enable and save
```

---

## Files Changed

### Backend
- `backend/models/sensor.py` - Added `skip_if_rained_today` field
- `backend/models/schedule.py` - Removed `skip_if_rained_today` field
- `backend/services/irrigation.py` - Fixed UTC bug + moved logic to read from sensor
- `backend/database/db.py` - Added migration

### Frontend
- `frontend/src/pages/SensorsPage.tsx` - Added checkbox for weather sensors
- `frontend/src/types/index.ts` - Updated interfaces
- `frontend/public/locales/{en,pl,de}/translation.json` - Added translations

### Testing
- `backend/test_irrigation.py` - NEW: comprehensive test suite (7 tests)
- `docker-compose.test.yml` - NEW: local Docker environment
- `test_mock_ha.py` - NEW: mock Home Assistant server
- `Dockerfile.mock-ha` - NEW: Docker image for mock HA
- `setup_test_env.sh` - NEW: setup script
- `TESTING.md` - NEW: detailed testing guide
- `IMPLEMENTATION.md` - NEW: full implementation summary

---

## How It Works

```
User enables "skip if it rained today" on weather sensor
              ↓
Schedule fires at 07:00
              ↓
start_zone() calls check_sensors_blocking()
              ↓
For each ENABLED weather/rain sensor:
  ├─ Read skip_if_rained_today config
  ├─ If TRUE: check history from local midnight
  │         └─ If rain found: return SkipReason.rain
  └─ If FALSE: continue
              ↓
If blocked → log skip, return error
If allowed → proceed with watering
```

---

## Key Improvements

| Before | After |
|--------|-------|
| Bug: UTC timezone broken | ✅ Fixed: correct "today" calculation |
| Checkbox in schedule (per-schedule) | ✅ Checkbox in sensor (per-sensor) |
| Only rain sensors checked | ✅ Both rain sensors + weather entities |
| No local testing | ✅ Full test suite + mock HA |

---

## Need Help?

See [TESTING.md](TESTING.md) for:
- Detailed debugging
- Troubleshooting
- More examples

Or [IMPLEMENTATION.md](IMPLEMENTATION.md) for:
- Technical deep dive
- All changes listed
- Architecture explanation

---

## Next: Deploy to HA

When you're ready:
1. Push to GitHub
2. Install from addon store as usual
3. Enjoy skip-if-rained-today feature! 🎉

---

**Everything ready to test locally!** 🚀
