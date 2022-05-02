"""General comfort_advisor constants."""
from datetime import timedelta
from typing import Final, Mapping

DOMAIN: Final = "comfort_advisor"

CONF_COMFORT: Final = "comfort"
CONF_DEVICE: Final = "device"
CONF_DEWPOINT_MAX: Final = "dew_point_max"
CONF_ENABLED_SENSORS: Final = "enabled_sensors"
CONF_HUMIDITY_MAX: Final = "humidity_max"
CONF_INDOOR_HUMIDITY: Final = "indoor_humidity"
CONF_INDOOR_TEMPERATURE: Final = "indoor_temperature"
CONF_INPUTS: Final = "inputs"
CONF_OUTDOOR_HUMIDITY: Final = "outdoor_humidity"
CONF_OUTDOOR_TEMPERATURE: Final = "outdoor_temperature"
CONF_POLL: Final = "poll"
CONF_POLLEN_MAX: Final = "pollen_max"
CONF_POLL_INTERVAL: Final = "poll_interval"
CONF_PROVIDER: Final = "provider"
CONF_PROVIDER_TYPE: Final = "provider_type"
CONF_SIMMER_INDEX_MAX: Final = "simmer_index_max"
CONF_SIMMER_INDEX_MIN: Final = "simmer_index_min"

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
DEFAULT_POLL: Final = False
DEFAULT_POLL_INTERVAL: Final = 30

# Device states
STATE_OPEN_WINDOWS: Final = "open_windows"
STATE_OPEN_WINDOWS_REASON: Final = "open_windows_reason"
STATE_HIGH_SIMMER_INDEX: Final = "high_simmer_index"
STATE_NEXT_CHANGE_TIME: Final = "next_change_time"

ALL_BINARY_SENSOR_TYPES = [STATE_OPEN_WINDOWS]
ALL_SENSOR_TYPES = [STATE_OPEN_WINDOWS_REASON, STATE_HIGH_SIMMER_INDEX, STATE_NEXT_CHANGE_TIME]

# can't be dynamic because providers are loaded on first use
PROVIDER_TYPES: Final[Mapping[str, str]] = {
    "fake": "Fake!",
    "nws": "National Weather Service",
    "tomorrowio": "Tomorrow.io",
}
