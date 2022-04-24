"""General comfort_advisor constants."""
from datetime import timedelta
from typing import Final
from homeassistant.const import Platform

DOMAIN = "comfort_advisor"
PLATFORMS = [Platform.SENSOR]
CONF_TEMPERATURE_SENSOR = "temperature_sensor"
CONF_HUMIDITY_SENSOR = "humidity_sensor"
CONF_POLL = "poll"

DEFAULT_NAME = "Comfort Advisor"
UPDATE_LISTENER = "update_listener"

# DataUpdateCoordinator constants
REALTIME_DATA_COORDINATOR: Final = "realtime"
FORECAST_DATA_COORDINATOR: Final = "forecast"
SCAN_INTERVAL_REALTIME = timedelta(minutes=15)
SCAN_INTERVAL_FORECAST = timedelta(hours=1)
