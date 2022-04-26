"""General comfort_advisor constants."""
from datetime import timedelta
from typing import Final

from homeassistant.const import Platform

DOMAIN = "comfort_advisor"
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]
CONF_POLL = "poll"

DEFAULT_NAME = "Comfort Advisor"
UPDATE_LISTENER = "update_listener"

ATTR_HUMIDITY = "humidity"
ATTR_FROST_RISK_LEVEL = "frost_risk_level"
CONF_ENABLED_SENSORS = "enabled_sensors"
CONF_SENSOR_TYPES = "sensor_types"
CONF_CUSTOM_ICONS = "custom_icons"
CONF_POLL_INTERVAL = "poll_interval"

CONF_WEATHER_PROVIDER = "weather_provider"
CONF_INDOOR_TEMPERATURE_SENSOR = "indoor_temp_sensor"
CONF_INDOOR_HUMIDITY_SENSOR = "indoor_humidity_sensor"
CONF_OUTDOOR_TEMPERATURE_SENSOR = "outdoor_temp_sensor"
CONF_OUTDOOR_HUMIDITY_SENSOR = "outdoor_humidity_sensor"
CONF_POLL = "poll"

# DataUpdateCoordinator constants
DATA_DEVICE: Final = "device"
DATA_REALTIME_SERVICE: Final = "realtime"
DATA_FORECAST_SERVICE: Final = "forecast"
SCAN_INTERVAL_REALTIME = timedelta(minutes=15)
SCAN_INTERVAL_FORECAST = timedelta(hours=1)

# Default values
POLL_DEFAULT = False
DEFAULT_POLL_INTERVAL = 30
