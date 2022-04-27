"""General comfort_advisor constants."""
from datetime import timedelta
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "comfort_advisor"
PLATFORMS: Final = [Platform.SENSOR, Platform.BINARY_SENSOR]

DEFAULT_NAME: Final = "Comfort Advisor"

CONF_ENABLED_SENSORS: Final = "enabled_sensors"
CONF_IN_HUMIDITY_ENTITY: Final = "in_humidity_sensor"
CONF_IN_TEMP_ENTITY: Final = "in_temperature_sensor"
CONF_OUT_HUMIDITY_ENTITY: Final = "out_humidity_sensor"
CONF_OUT_TEMP_ENTITY: Final = "out_temperature_sensor"
CONF_POLL: Final = "poll"
CONF_POLL_INTERVAL: Final = "poll_interval"
CONF_SENSOR_TYPES: Final = "sensor_types"
CONF_WEATHER_PROVIDER: Final = "weather_provider"

# DataUpdateCoordinator constants
SCAN_INTERVAL_REALTIME: Final = timedelta(minutes=15)
SCAN_INTERVAL_FORECAST: Final = timedelta(hours=1)

# Default values
POLL_DEFAULT: Final = False
DEFAULT_POLL_INTERVAL: Final = 30

WEATHER_PROVIDER_NAMES: Final = {
    "tomorrowio": "Tomorrow.io",
    # "nws": "National Weather Service",
    "fake": "Fake!",
}
