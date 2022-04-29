"""General comfort_advisor constants."""
from datetime import timedelta
from typing import Final

from homeassistant.backports.enum import StrEnum

DOMAIN: Final = "comfort_advisor"

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


class ConfigValue(StrEnum):
    """Configuration value enum."""

    DEWPOINT_MAX = "dewpoint_max"
    ENABLED_SENSORS = "enabled_sensors"
    HUMIDITY_MAX = "humidity_max"
    IN_HUMIDITY_SENSOR = "in_humidity_sensor"
    IN_TEMP_SENSOR = "in_temp_sensor"
    NAME = "name"
    OUT_HUMIDITY_SENSOR = "out_humidity_sensor"
    OUT_TEMP_SENSOR = "out_temp_sensor"
    POLL = "poll"
    POLL_INTERVAL = "poll_interval"
    POLLEN_MAX = "pollen_max"
    PROVIDER_TYPE = "provider_type"
    SIMMER_INDEX_MAX = "simmer_index_max"
    SIMMER_INDEX_MIN = "simmer_index_min"
    WEATHER_PROVIDER = "weather_provider"


SENSOR_TYPES: Final = ["open_windows", "open_windows_reason"]  # TODO: make dynamic

WEATHER_PROVIDER_TYPES: Final = {
    "tomorrowio": "Tomorrow.io",
    "nws": "National Weather Service",
    "fake": "Fake!",
}
