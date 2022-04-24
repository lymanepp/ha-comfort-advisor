"""General comfort_advisor constants."""
from homeassistant.const import Platform

DOMAIN = "comfort_advisor"
PLATFORMS = [Platform.SENSOR]
CONF_TEMPERATURE_SENSOR = "temperature_sensor"
CONF_HUMIDITY_SENSOR = "humidity_sensor"
CONF_POLL = "poll"

DEFAULT_NAME = "Comfort Advisor"
UPDATE_LISTENER = "update_listener"
