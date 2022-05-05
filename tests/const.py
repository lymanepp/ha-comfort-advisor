"""General test constants."""

from typing import Any

from homeassistant.const import CONF_NAME

from custom_components.comfort_advisor.const import (
    CONF_ENABLED_SENSORS,
    CONF_INDOOR_HUMIDITY,
    CONF_INDOOR_TEMPERATURE,
    CONF_OUTDOOR_HUMIDITY,
    CONF_OUTDOOR_TEMPERATURE,
)

USER_INPUT: dict[str, Any] = {
    CONF_INDOOR_TEMPERATURE: "sensor.test_temperature_sensor",
    CONF_INDOOR_HUMIDITY: "sensor.test_humidity_sensor",
    CONF_OUTDOOR_TEMPERATURE: "sensor.test_temperature_sensor",
    CONF_OUTDOOR_HUMIDITY: "sensor.test_humidity_sensor",
    CONF_NAME: "New name",
}

ADVANCED_USER_INPUT = {
    **USER_INPUT,
    CONF_NAME: "test_comfort_advisor",
    CONF_ENABLED_SENSORS: [],
}
