# Irrigation BSS

Advanced irrigation management for Home Assistant. Control your garden watering system with zones, schedules, sensors and weather-based automation — all from the HA sidebar.

## Installation

1. Go to **Settings → Add-ons → Add-on Store → ⋮ → Custom repositories**
2. Add `https://github.com/BSS-Baumgart/bss_ha_irrigation`
3. Install **Irrigation BSS**
4. Configure `language` and `log_level` on the **Configuration** tab
5. Start the addon — it appears in the HA sidebar automatically

The addon connects to Home Assistant via the Supervisor. No token or URL configuration is required.

## Configuration

| Option | Values | Default | Description |
|--------|--------|---------|-------------|
| `log_level` | debug / info / warning / error | info | Backend log verbosity |
| `language` | pl / en / de | en | Default UI language on fresh install |

UI language follows the addon configuration.

## Getting started

### 1. Add valves
Go to **Valves** and add the HA entities that control your solenoid valves (switches or input_boolean). The name is filled in automatically from HA.

### 2. Create zones
Go to **Zones** and create a zone for each area you want to water independently. Assign one or more valves to each zone.

### 3. Add sensors (optional)
Go to **Sensors** to add:
- **Rain sensor** — skips watering when active
- **Soil moisture** — skips when soil is wet above a threshold
- **Temperature** — frost protection (skips below 2 °C by default)
- **Flow meter** — monitors water usage
- **Weather** — forecast-based skip via HA weather entity

### 4. Set a schedule
Go to **Schedule** and create a schedule for each zone — choose days of the week, start time, duration and watering mode (sequential or parallel).

### 5. Dashboard
The dashboard shows live zone status, countdown timers, blocking sensor alerts and a quick-start grid for manual watering.

## Watering modes

- **Sequential** — zones water one at a time. Recommended for systems with limited water pressure.
- **Parallel** — all zones in a schedule water simultaneously.

## Virtual entities

The addon publishes its state back to Home Assistant as entities you can use in dashboards and automations:

- `binary_sensor.irrigation_bss_watering` — any zone active
- `sensor.irrigation_bss_watering_status` — watering status with localized text and reason
  - state values: `active`, `rain_blocked`, `frost_protection`, `inactive`
  - if active, display text becomes e.g. `Aktywne - Dom tył` or `Active - Back yard`
  - attributes: `status_reason`, `state_value`, `active`, `active_zone`, `remaining_sec`, `next_run`, `status_text`
- `sensor.irrigation_bss_active_zone` — active zone name
- `sensor.irrigation_bss_remaining_sec` — remaining seconds
- `sensor.irrigation_bss_next_watering` — next scheduled run
- `binary_sensor.irrigation_bss_rain_blocked` — rain sensor blocking
- `binary_sensor.irrigation_bss_frost_blocked` — frost protection active
- `binary_sensor.irrigation_bss_zone_{id}` — per-zone state

## Languages

The UI is available in **Polish**, **English** and **German**. The language set in addon configuration is used by the UI.

To contribute a translation, add `frontend/public/locales/{lang}/translation.json` based on the English template.
