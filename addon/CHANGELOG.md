## 3.4
- **Smart Watering (ET0)**: Added dynamic watering duration adjustment based on Evapotranspiration (ET0) from Open-Meteo. The system now automatically scales the watering time up or down depending on temperature, sun, and recent rainfall.
- **Baseline Time Calculator**: Added a built-in UI calculator on the Zone page to mathematically compute the ideal baseline watering time (`duration_min`) based on the zone area (m²), flow rate (L/min), soil type (efficiency), and sun exposure. This ensures the baseline time is perfectly calibrated for the 4.0mm ET0 target.
- **Force Run ("Podlej mimo to")**: Added the ability to manually override a skipped schedule. If a schedule is blocked by rain or soil sensors, a new "Water anyway" button appears next to the skipped badge, allowing you to force the scheduled run once.
- **Fix**: Smart Watering scale was never applied because `get_smart_scale()` tried to read lat/lon from a non-existent config field instead of the `app_settings` DB table. The error was silently caught, resulting in the base duration always being used unchanged. Now correctly reads coordinates from the Weather page settings.

## 2.0.0 (Nawo Fork Major Release)

### ✨ New Features & UI Overhaul
- **Granular Weather Controls**: Moved `skip_if_raining` and `skip_if_rained_today` settings from a global Weather configuration to a per-schedule configuration. You can now define precisely which schedules should skip on rain.
- **Smart Status Display**: Removed the distracting second-by-second countdown. The dashboard now displays clean, friendly statuses ("Planowane", "W trakcie").
- **Rain Skip Awareness**: If a schedule is known to be skipped due to rain, the countdown is entirely hidden and replaced with a clear "Pominięte z powodu deszczu" (Skipped due to rain) status on both the Dashboard and Schedule views.
- **Enhanced Status Sensor**: `sensor.irrigation_bss_watering_status` now publishes localized status text and active zone names (e.g. `Aktywne - Dom tył`) with machine-readable `state_value`. Localized watering status display follows the addon language setting (`pl`/`en`/`de`).
- **Rain History Skip (`skip_if_rained_today`)**: Introduced a feature to block watering if it has rained earlier in the day by parsing HA weather entity history since local midnight. Prevents timezone-related bugs by using correct local-to-UTC conversion.

### 🛡 Security & Fail-Safe
- **Sensor Fail-Safe Mechanism**: If a Home Assistant sensor (soil moisture, temperature, flow) returns an invalid or broken numeric value, the addon now safely blocks watering (`ha_unavailable`) instead of silently ignoring the block.
- **Hardened CORS Policy**: Removed insecure wildcard `*` CORS origins, restricting access strictly to local environments and secure Home Assistant Ingress origins, protecting against CSRF attacks.

### ⚡ Performance & Architecture Optimizations
- **N+1 Query Elimination**: Massively optimized SQLite database queries on the `/api/zones` endpoints by using SQL JOINs with `func.count()`. The UI now loads instantly without spamming the database with dozens of separate valve queries.
- **Optimized SQLite Sessions**: Re-architected backend helpers to accept existing database sessions rather than opening and closing new ones in tight loops, significantly reducing SQLite overhead during start/stop operations.
- **Codebase Cleanup (Breaking Change)**: Completely removed the legacy, manual SQLite migrations system. The repository is now clean and relies purely on standard `SQLModel.metadata.create_all()` for fresh installations.

### 🌍 Localization
- **Complete Translations**: Updated English (`en`), Polish (`pl`), and German (`de`) locales with new strings for schedule skip conditions, weather statuses, and friendly dashboard text.

## 1.4.4

- Fixed: Color theme settings now correctly update the UI in real-time — all background, surface, border, button, badge, and accent elements respond to custom colour changes.
- Changed: Removed the dark/light mode toggle from the sidebar — the app always uses dark mode; colours are customised via Settings.
- New: 4 preset colour palettes in Settings: Default (Green), Ocean (Blue), Sunset (Orange), Violet — one click applies and saves all 6 colours instantly.

## 1.4.3

- Fixed: Flow meter sensor now correctly reports "Unexpected flow" (instead of "Wet soil") in irrigation history.
- Fixed: Safety sweep — all zone valves are explicitly closed when the last active zone finishes (prevents stuck-open valves).
- Fixed: Manual start now supports a "Force start" option to bypass active sensor blocks (soil, rain, frost, flow).
- New: Pump control — configure a pump entity (e.g. well pump) that starts automatically with the first section and stops after the last, mirroring main valve behaviour.
- New: Settings page — language selector (EN/PL/DE) and 6 customisable interface colours (hex input + colour picker), all persisted to the database.

## 1.4.2

- Fixed: HA WebSocket "Cannot write to closing transport" error after Home Assistant restart — sends are now guarded by a connection-state flag that is only set after successful `auth_ok`.
- Fixed: reconnect loop now retries indefinitely (every 5 s) until HA is back, instead of failing permanently on the first attempt after a restart.
- Fixed: pending WebSocket futures are cancelled on disconnect to prevent hangs or stale callbacks.
- Fixed: old aiohttp session is now properly closed before opening a new one on reconnect.

## 1.4.1

- Fixed: startup crash on existing installations after upgrade to v1.4.0 — missing `extra_zone_ids` column in the SQLite database is now added automatically via a migration on startup.
- Fixed: removed deprecated `baseUrl` from frontend TypeScript configuration.

## 1.4.0

- Fixed: history timestamps are now displayed in local time (were incorrectly shown as UTC).
- Fixed: entity picker in edit mode now shows the currently saved entity (valve / sensor).
- Improved: section cards now display the list of assigned valves with a hint when none are assigned.
- Improved: sensor skip logic now correctly uses per-schedule flags (skip_if_rain / skip_if_soil_wet / skip_if_frost).
- Improved: flow meter and weather entity sensors now participate in watering skip evaluation.
- Improved: sensor form now shows a description and threshold hint for each sensor type.
- New: multi-zone sequential schedules — select multiple sections in one schedule entry and they will run one after another automatically.

## 1.3.4

- Added CI validation workflow for frontend build on pull requests (develop and master).
- Updated project documentation for Home Assistant users and release workflow clarity.
- Added UI screenshots to repository documentation.

## 1.3.3

- Added dashboard quick actions: select section and start watering with custom duration.
- Added start modal on dashboard section cards to set watering time before manual start.
- Minor dashboard UX cleanup for active watering remaining time label.

## 1.3.2

- Improved sensors UI: current values are now user-friendly with translated states and units.
- Improved main valve section layout on Valves page for cleaner, more compact appearance.
- Removed language switcher from sidebar; UI language now follows addon configuration.

## 1.3.1

- Fixed: resolved backend 500 errors on irrigation status/start/stop endpoints during active watering.
- Fixed: improved robustness of valve and main valve service calls to avoid unhandled runtime failures.
- Fixed: header/dashboard watering state now has API polling fallback, so Stop All and active state remain visible even when WebSocket events are delayed.

## 1.3.0

- Fixed: header bar now correctly shows active watering status via WebSocket (active_zones included in zone_started/zone_stopped events)
- Added: main valve support — configure a master valve entity that opens before the first section starts and closes after the last section stops
- Dashboard: sections shown as cards with valve count, next schedule time, and inline progress bar when watering
- Renamed: "zones" → "sections" across the entire UI (PL: sekcje, EN: sections, DE: Sektionen)

## 1.2.0

- Fixed light mode — all pages now readable (white text on white background resolved)
- Weather settings (source, lat/lon, HA entity) persist across addon restarts in SQLite
- New `/api/settings` key-value store in addon database — all settings survive restarts
- Weather page: auto-saves lat/lon/source as you type (debounced 600 ms)
- Weather page: loads saved settings on mount before triggering first forecast fetch

## 1.1.0

- Mobile-responsive UI — sidebar slides in from the left on small screens
- Collapsible sidebar with hamburger menu in the header
- Dark / light mode toggle in the sidebar
- UI language now syncs from addon configuration on restart
- Language switcher in the sidebar saves user preference across restarts
- App icon displayed in the sidebar header
- Fixed HA Ingress asset paths (CSS/JS 404 on first install)
- Fixed translation files returning 404 through Ingress proxy
- Fixed WebSocket and API calls routing through Ingress base path
- Removed ha_url and ha_token from addon options — Supervisor provides these automatically

## 1.0.0

- Initial release
- Zone management with color labels and manual start
- Valve assignment from HA entity picker
- Sensor support: rain, soil moisture, temperature, flow meter, weather
- Weekly scheduler with sequential and parallel watering modes
- Weather-based skip via HA weather entity
- Virtual entities published to HA for dashboards and automations
- Real-time WebSocket status updates
- UI in Polish, English and German
