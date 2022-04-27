"""General test constants."""
from homeassistant.const import CONF_NAME

from custom_components.comfort_advisor.const import (
    CONF_ENABLED_SENSORS,
    CONF_IN_HUMIDITY_ENTITY,
    CONF_IN_TEMP_ENTITY,
    CONF_OUT_HUMIDITY_ENTITY,
    CONF_OUT_TEMP_ENTITY,
    CONF_POLL,
    CONF_POLL_INTERVAL,
)

USER_INPUT = {
    CONF_NAME: "New name",
    CONF_IN_TEMP_ENTITY: "sensor.test_temperature_sensor",
    CONF_IN_HUMIDITY_ENTITY: "sensor.test_humidity_sensor",
    CONF_OUT_TEMP_ENTITY: "sensor.test_temperature_sensor",
    CONF_OUT_HUMIDITY_ENTITY: "sensor.test_humidity_sensor",
    CONF_POLL: False,
    CONF_POLL_INTERVAL: 30,
}

ADVANCED_USER_INPUT = {
    **USER_INPUT,
    CONF_NAME: "test_comfort_advisor",
    CONF_ENABLED_SENSORS: [],
}
