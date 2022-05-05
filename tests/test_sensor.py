"""The test for the Comfort Advisor sensor platform."""
import logging

from homeassistant.components.command_line.const import DOMAIN as COMMAND_LINE_DOMAIN
from homeassistant.components.sensor import DOMAIN as PLATFORM_DOMAIN
import pytest

from custom_components.comfort_advisor.const import ALL_SENSOR_TYPES, DOMAIN

_LOGGER = logging.getLogger(__name__)

TEST_NAME = "sensor.test_comfort_advisor"

INDOOR_TEMP_TEST_SENSOR = {
    "platform": COMMAND_LINE_DOMAIN,
    "command": "echo 0",
    "name": "test_indoor_temp_sensor",
    "value_template": "{{ 25.0 | float }}",
}

INDOOR_HUMIDITY_TEST_SENSOR = {
    "platform": COMMAND_LINE_DOMAIN,
    "command": "echo 0",
    "name": "test_indoor_humidity_sensor",
    "value_template": "{{ 50.0 | float }}",
}

OUTDOOR_TEMP_TEST_SENSOR = {
    "platform": COMMAND_LINE_DOMAIN,
    "command": "echo 0",
    "name": "test_outdoor_temp_sensor",
    "value_template": "{{ 20.0 | float }}",
}

OUTDOOR_HUMIDITY_TEST_SENSOR = {
    "platform": COMMAND_LINE_DOMAIN,
    "command": "echo 0",
    "name": "test_outdoor_humidity_sensor",
    "value_template": "{{ 55.0 | float }}",
}

DEFAULT_TEST_SENSORS = [
    "domains, config",
    [
        (
            [(PLATFORM_DOMAIN, 4)],
            {
                PLATFORM_DOMAIN: [
                    INDOOR_TEMP_TEST_SENSOR,
                    INDOOR_HUMIDITY_TEST_SENSOR,
                    OUTDOOR_TEMP_TEST_SENSOR,
                    OUTDOOR_HUMIDITY_TEST_SENSOR,
                    {
                        "platform": DOMAIN,
                        "sensors": {
                            "test_comfort_advisor": {
                                "indoor_temp_sensor": "sensor.test_indoor_temp_sensor",
                                "indoor_humidity_sensor": "sensor.test_indoor_humidity_sensor",
                                "outdoor_temp_sensor": "sensor.test_outdoor_temp_sensor",
                                "outdoor_humidity_sensor": "sensor.test_outdoor_humidity_sensor",
                            },
                        },
                    },
                ],
            },
        ),
        (
            [(PLATFORM_DOMAIN, 4), (DOMAIN, 1)],
            {
                PLATFORM_DOMAIN: [
                    INDOOR_TEMP_TEST_SENSOR,
                    INDOOR_HUMIDITY_TEST_SENSOR,
                    OUTDOOR_TEMP_TEST_SENSOR,
                    OUTDOOR_HUMIDITY_TEST_SENSOR,
                ],
                DOMAIN: {
                    PLATFORM_DOMAIN: {
                        "name": "test_comfort_advisor",
                        "api_key": "test_api_key",
                        "indoor_temp_sensor": "sensor.test_indoor_temp_sensor",
                        "indoor_humidity_sensor": "sensor.test_indoor_humidity_sensor",
                        "outdoor_temp_sensor": "sensor.test_outdoor_temp_sensor",
                        "outdoor_humidity_sensor": "sensor.test_outdoor_humidity_sensor",
                    },
                },
            },
        ),
    ],
]

ALL_SENSOR_TYPES = sorted(ALL_SENSOR_TYPES)
LEN_DEFAULT_SENSORS = len(ALL_SENSOR_TYPES)


@pytest.mark.parametrize(*DEFAULT_TEST_SENSORS)
async def test_config(hass, start_ha):
    """Test basic config."""
    assert len(hass.states.async_all(PLATFORM_DOMAIN)) == LEN_DEFAULT_SENSORS + 2
