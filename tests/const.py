"""General test constants."""
from homeassistant.const import CONF_NAME

from custom_components.comfort_advisor.const import (
    CONF_ENABLED_SENSORS,
    CONF_INDOOR_HUMIDITY_SENSOR,
    CONF_INDOOR_TEMPERATURE_SENSOR,
    CONF_OUTDOOR_HUMIDITY_SENSOR,
    CONF_OUTDOOR_TEMPERATURE_SENSOR,
    CONF_POLL,
    CONF_POLL_INTERVAL,
)

USER_INPUT = {
    CONF_NAME: "New name",
    CONF_INDOOR_TEMPERATURE_SENSOR: "sensor.test_temperature_sensor",
    CONF_INDOOR_HUMIDITY_SENSOR: "sensor.test_humidity_sensor",
    CONF_OUTDOOR_TEMPERATURE_SENSOR: "sensor.test_temperature_sensor",
    CONF_OUTDOOR_HUMIDITY_SENSOR: "sensor.test_humidity_sensor",
    CONF_POLL: False,
    CONF_POLL_INTERVAL: 30,
}

ADVANCED_USER_INPUT = {
    **USER_INPUT,
    CONF_NAME: "test_comfort_advisor",
    CONF_ENABLED_SENSORS: [],
}
