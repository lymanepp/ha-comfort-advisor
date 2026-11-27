"""General comfort_advisor constants."""

from logging import Logger, getLogger
from typing import Final

_LOGGER: Logger = getLogger(__package__)

DOMAIN: Final = "comfort_advisor"

CONF_WEATHER: Final = "weather"
CONF_INDOOR_HUMIDITY: Final = "indoor_humidity"
CONF_INDOOR_TEMPERATURE: Final = "indoor_temperature"
CONF_OUTDOOR_HUMIDITY: Final = "outdoor_humidity"
CONF_OUTDOOR_TEMPERATURE: Final = "outdoor_temperature"
CONF_POLLEN: Final = "pollen"
CONF_ENABLED_SENSORS: Final = "enabled_sensors"

# Default values
DEFAULT_NAME: Final = "Comfort Advisor"
DEFAULT_MANUFACTURER: Final = "@lymanepp"

# Input changes arriving within this many seconds (e.g. temperature and humidity
# published together) are combined into one recalculation.
INPUT_COOLDOWN: Final = 1.0
