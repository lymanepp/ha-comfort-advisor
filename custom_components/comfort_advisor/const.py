"""General comfort_advisor constants."""
from datetime import timedelta
from typing import Final

from homeassistant.const import Platform

DOMAIN = "comfort_advisor"
PLATFORMS = [Platform.SENSOR]
CONF_POLL = "poll"

DEFAULT_NAME = "Comfort Advisor"
UPDATE_LISTENER = "update_listener"

CONF_WEATHER_PROVIDER: Final = "weather_provider"

# DataUpdateCoordinator constants
REALTIME_SERVICE: Final = "realtime"
FORECAST_SERVICE: Final = "forecast"
SCAN_INTERVAL_REALTIME = timedelta(minutes=15)
SCAN_INTERVAL_FORECAST = timedelta(hours=1)
