"""General comfort_advisor constants."""
from datetime import timedelta
from typing import Final, Mapping

from homeassistant.backports.enum import StrEnum

DOMAIN: Final = "comfort_advisor"


class ConfigSection(StrEnum):  # type: ignore
    """TODO."""

    INPUTS = "inputs"
    PROVIDER = "provider"
    COMFORT = "comfort"
    DEVICE = "device"


class ConfigInputs(StrEnum):  # type: ignore
    """TODO."""

    INDOOR_HUMIDITY = "indoor_humidity"
    INDOOR_TEMPERATURE = "indoor_temperature"
    INPUTS = "inputs"
    OUTDOOR_HUMIDITY = "outdoor_humidity"
    OUTDOOR_TEMPERATURE = "outdoor_temperature"


class ConfigProvider(StrEnum):  # type: ignore
    """TODO."""

    TYPE = "type"
    API_KEY = "api_key"
    LOCATION = "location"


class ConfigComfort(StrEnum):  # type: ignore
    """TODO."""

    DEW_POINT_MAX = "dew_point_max"
    HUMIDITY_MAX = "humidity_max"
    POLLEN_MAX = "pollen_max"
    SIMMER_INDEX_MAX = "simmer_index_max"
    SIMMER_INDEX_MIN = "simmer_index_min"


class ConfigDevice(StrEnum):  # type: ignore
    """TODO."""

    NAME = "name"
    ENABLED_SENSORS = "enabled_sensors"


# TODO: remove these
CONF_COMFORT: Final = ConfigSection.COMFORT
CONF_DEVICE: Final = ConfigSection.DEVICE
CONF_INPUTS: Final = ConfigSection.INPUTS
CONF_PROVIDER: Final = ConfigSection.PROVIDER

# TODO: and these
CONF_INDOOR_HUMIDITY: Final = ConfigInputs.INDOOR_HUMIDITY
CONF_INDOOR_TEMPERATURE: Final = ConfigInputs.INDOOR_TEMPERATURE
CONF_OUTDOOR_HUMIDITY: Final = ConfigInputs.OUTDOOR_HUMIDITY
CONF_OUTDOOR_TEMPERATURE: Final = ConfigInputs.OUTDOOR_TEMPERATURE
CONF_DEW_POINT_MAX: Final = ConfigComfort.DEW_POINT_MAX
CONF_HUMIDITY_MAX: Final = ConfigComfort.HUMIDITY_MAX
CONF_POLLEN_MAX: Final = ConfigComfort.POLLEN_MAX
CONF_SIMMER_INDEX_MAX: Final = ConfigComfort.SIMMER_INDEX_MAX
CONF_SIMMER_INDEX_MIN: Final = ConfigComfort.SIMMER_INDEX_MIN
CONF_ENABLED_SENSORS: Final = ConfigDevice.ENABLED_SENSORS

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
DEFAULT_POLL_INTERVAL: Final = 60

# can't be dynamic because providers are loaded on first use
PROVIDER_TYPES: Final[Mapping[str, str]] = {
    "fake": "Fake!",
    "nws": "National Weather Service",
    "tomorrowio": "Tomorrow.io",
}
