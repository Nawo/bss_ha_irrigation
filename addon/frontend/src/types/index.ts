export interface Zone {
  id: number
  name: string
  color: string
  description?: string
  duration_min: number
  sequence_order: number
  enabled: boolean
  area_m2?: number
  flow_lpm?: number
  soil_type?: string
  sun_exposure?: string
  valve_count: number
  is_watering: boolean
}

export interface Valve {
  id: number
  name: string
  entity_id: string
  zone_id?: number
  zone_name?: string
  enabled: boolean
  notes?: string
  ha_state?: 'on'|'off'|'unavailable'|string
}

export type SensorType = 'rain'|'soil'|'flow'|'temperature'

export interface Sensor {
  id: number
  name: string
  entity_id: string
  sensor_type: SensorType
  threshold?: number
  enabled: boolean
  notes?: string
  ha_state?: string
  is_blocking: boolean
  skip_if_rained_today: boolean
  rained_today?: boolean
}

export type WateringMode = 'sequential'|'parallel'

export interface Schedule {
  id: number
  zone_id: number
  extra_zone_ids?: string  // comma-separated extra zone IDs
  all_zone_ids?: number[]  // resolved list from backend
  zone_name?: string
  weekdays: number    // bitmask
  start_time: string  // "HH:MM"
  duration_override_min?: number
  mode: WateringMode
  enabled: boolean
  skip_if_raining: boolean
  skip_if_rained_today: boolean
  skip_if_soil_wet: boolean
  skip_if_frost: boolean
  force_next_run?: boolean
  smart_watering?: boolean
  next_run?: string
  next_run_will_be_skipped?: boolean
  next_run_skipped_reason?: string
}

export type SkipReason =
    'rain'|'soil_wet'|'frost'|'manual_stop'|'ha_unavailable'
export type TriggerSource = 'schedule'|'manual'

export interface WateringLog {
  id: number
  zone_id?: number
  zone_name: string
  started_at: string
  ended_at?: string
  duration_sec?: number
  triggered_by: TriggerSource
  skipped: boolean
  skip_reason?: SkipReason
  water_liters?: number
}

export interface ActiveZone {
  zone_id: number
  zone_name: string
  started_at: string
  duration_min: number
  elapsed_sec: number
  remaining_sec: number
}

export interface IrrigationStatus {
  active_zones: ActiveZone[]
  any_watering: boolean
}

export interface HAEntity {
  entity_id: string
  friendly_name: string
  state: string
  domain: string
  unit?: string
  device_class?: string
}

export interface WeatherData {
  condition: string
  temperature?: number
  rain_expected_24h: boolean
  forecast: WeatherForecastItem[]
}

export interface WeatherForecastItem {
  datetime: string
  condition: string
  temperature?: number
}
