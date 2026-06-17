"""
Shared constants used across backend services and routers.
"""

# Weather condition states that indicate precipitation (rain/snow/hail).
# Used by sensors, irrigation blocking logic, and HA publisher.
RAIN_WEATHER_STATES: frozenset[str] = frozenset({
    "rainy", "pouring", "snowy", "snowy-rainy", "lightning-rainy", "hail",
})
