"""General test constants."""

from typing import Any

from custom_components.comfort_advisor.const import ConfigValue

USER_INPUT: dict[str, Any] = {
    str(ConfigValue.NAME): "New name",
    str(ConfigValue.INDOOR_TEMPERATURE): "sensor.test_temperature_sensor",
    str(ConfigValue.INDOOR_HUMIDITY): "sensor.test_humidity_sensor",
    str(ConfigValue.OUTDOOR_TEMPERATURE): "sensor.test_temperature_sensor",
    str(ConfigValue.OUTDOOR_HUMIDITY): "sensor.test_humidity_sensor",
    str(ConfigValue.POLL): False,
    str(ConfigValue.POLL_INTERVAL): 30,
}

ADVANCED_USER_INPUT = {
    **USER_INPUT,
    str(ConfigValue.NAME): "test_comfort_advisor",
    str(ConfigValue.ENABLED_SENSORS): [],
}
