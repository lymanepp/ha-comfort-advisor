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
CONF_DEW_POINT_MAX: Final = "dew_point_max"
CONF_HUMIDITY_MAX: Final = "humidity_max"
CONF_POLLEN_MAX: Final = "pollen_max"
CONF_SIMMER_INDEX_MAX: Final = "simmer_index_max"
CONF_SIMMER_INDEX_MIN: Final = "simmer_index_min"
CONF_ENABLED_SENSORS: Final = "enabled_sensors"
CONF_COOLING_TEMPERATURE_MIN: Final = "cooling_temperature_min"
CONF_TEMPERATURE_TOLERANCE: Final = "temperature_tolerance"
CONF_HYSTERESIS: Final = "hysteresis"
CONF_HUMIDITY_HYSTERESIS: Final = "humidity_hysteresis"

# Default values
DEFAULT_NAME: Final = "Comfort Advisor"
DEFAULT_MANUFACTURER: Final = "@lymanepp"
DEFAULT_DEWPOINT_MAX: Final = 60
DEFAULT_HUMIDITY_MAX: Final = 95
DEFAULT_POLLEN_MAX: Final = 2
DEFAULT_SIMMER_INDEX_MAX: Final = 85
DEFAULT_SIMMER_INDEX_MIN: Final = 70
DEFAULT_COOLING_TEMPERATURE_MIN: Final = 60  # °F
DEFAULT_TEMPERATURE_TOLERANCE: Final = 1  # °F interval
DEFAULT_HYSTERESIS: Final = 1  # °F interval
DEFAULT_HUMIDITY_HYSTERESIS: Final = 2  # percentage points

# Input changes arriving within this many seconds (e.g. temperature and humidity
# published together) are combined into one recalculation.
INPUT_COOLDOWN: Final = 1.0

# Decimal places for published temperature and enthalpy values, so tiny input
# changes don't record new states.
OUTPUT_PRECISION: Final = 1
