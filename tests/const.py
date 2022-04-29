"""General test constants."""

from typing import Any

from custom_components.comfort_advisor.const import ConfigValue

USER_INPUT: dict[str, Any] = {
    str(ConfigValue.NAME): "New name",
    str(ConfigValue.IN_TEMP_SENSOR): "sensor.test_temperature_sensor",
    str(ConfigValue.IN_HUMIDITY_SENSOR): "sensor.test_humidity_sensor",
    str(ConfigValue.OUT_TEMP_SENSOR): "sensor.test_temperature_sensor",
    str(ConfigValue.OUT_HUMIDITY_SENSOR): "sensor.test_humidity_sensor",
    str(ConfigValue.POLL): False,
    str(ConfigValue.POLL_INTERVAL): 30,
}

ADVANCED_USER_INPUT = {
    **USER_INPUT,
    str(ConfigValue.NAME): "test_comfort_advisor",
    str(ConfigValue.ENABLED_SENSORS): [],
}
