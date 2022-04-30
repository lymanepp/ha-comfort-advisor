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


class ConfigSchema(StrEnum):  # type: ignore
    """Configuration section enum."""

    PROVIDER = "provider"
    INPUTS = "inputs"
    COMFORT = "comfort"
    DEVICE = "device"


class ConfigValue(StrEnum):  # type: ignore
    """Configuration value enum."""

    DEWPOINT_MAX = "dew_point_max"
    ENABLED_SENSORS = "enabled_sensors"
    HUMIDITY_MAX = "humidity_max"
    INDOOR_HUMIDITY = "indoor_humidity"
    INDOOR_TEMPERATURE = "indoor_temperature"
    NAME = "name"
    OUTDOOR_HUMIDITY = "outdoor_humidity"
    OUTDOOR_TEMPERATURE = "outdoor_temperature"
    POLL = "poll"
    POLL_INTERVAL = "poll_interval"
    POLLEN_MAX = "pollen_max"
    TYPE = "type"
    SIMMER_INDEX_MAX = "simmer_index_max"
    SIMMER_INDEX_MIN = "simmer_index_min"


SENSOR_TYPES: Final = ["open_windows", "open_windows_reason"]  # TODO: make dynamic

PROVIDER_TYPES: Final = {
    "fake": "Fake!",
    "nws": "National Weather Service",
    "tomorrowio": "Tomorrow.io",
}
