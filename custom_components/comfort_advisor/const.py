"""General comfort_advisor constants."""
from datetime import timedelta
from typing import Final

DOMAIN: Final = "comfort_advisor"

CONF_INDOOR_HUMIDITY: Final = "indoor_humidity"
CONF_INDOOR_TEMPERATURE: Final = "indoor_temperature"
CONF_OUTDOOR_HUMIDITY: Final = "outdoor_humidity"
CONF_OUTDOOR_TEMPERATURE: Final = "outdoor_temperature"
CONF_DEW_POINT_MAX: Final = "dew_point_max"
CONF_HUMIDITY_MAX: Final = "humidity_max"
CONF_POLLEN_MAX: Final = "pollen_max"
CONF_PROVIDER: Final = "provider"
CONF_WEATHER: Final = "weather"
CONF_SIMMER_INDEX_MAX: Final = "simmer_index_max"
CONF_SIMMER_INDEX_MIN: Final = "simmer_index_min"
CONF_ENABLED_SENSORS: Final = "enabled_sensors"

# DataUpdateCoordinator constants
SCAN_INTERVAL_REALTIME: Final = timedelta(minutes=15)
SCAN_INTERVAL_FORECAST: Final = timedelta(hours=1)

# Default values
DEFAULT_NAME: Final = "Comfort Advisor"
DEFAULT_MANUFACTURER: Final = "@lymanepp"
DEFAULT_DEWPOINT_MAX: Final = 60
DEFAULT_HUMIDITY_MAX: Final = 95
DEFAULT_POLLEN_MAX: Final = 2
DEFAULT_SIMMER_INDEX_MAX: Final = 85
DEFAULT_SIMMER_INDEX_MIN: Final = 70
DEFAULT_POLL_INTERVAL: Final = 30
