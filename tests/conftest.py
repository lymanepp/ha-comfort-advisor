"""Shared fixtures for Comfort Advisor tests."""

from datetime import timedelta
from typing import Any

from homeassistant.components.weather import DOMAIN as WEATHER_DOMAIN
from homeassistant.components.weather import Forecast, WeatherEntity, WeatherEntityFeature
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_NAME,
    CONF_PLATFORM,
    CONF_TEMPERATURE_UNIT,
    PERCENTAGE,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    setup_test_component_platform,
)

from custom_components.comfort_advisor.comfort import Calculated
from custom_components.comfort_advisor.const import (
    CONF_COOLING_TEMPERATURE_MIN,
    CONF_DEW_POINT_MAX,
    CONF_ENABLED_SENSORS,
    CONF_HUMIDITY_MAX,
    CONF_INDOOR_HUMIDITY,
    CONF_INDOOR_TEMPERATURE,
    CONF_OUTDOOR_HUMIDITY,
    CONF_OUTDOOR_TEMPERATURE,
    CONF_POLLEN_MAX,
    CONF_SIMMER_INDEX_MAX,
    CONF_SIMMER_INDEX_MIN,
    CONF_TEMPERATURE_TOLERANCE,
    CONF_WEATHER,
    DOMAIN,
)

WEATHER_ENTITY = "weather.test_weather"
INDOOR_TEMPERATURE = "sensor.indoor_temperature"
INDOOR_HUMIDITY = "sensor.indoor_humidity"
OUTDOOR_TEMPERATURE = "sensor.outdoor_temperature"
OUTDOOR_HUMIDITY = "sensor.outdoor_humidity"

INPUTS: dict[str, Any] = {
    CONF_WEATHER: WEATHER_ENTITY,
    CONF_INDOOR_TEMPERATURE: INDOOR_TEMPERATURE,
    CONF_INDOOR_HUMIDITY: INDOOR_HUMIDITY,
    CONF_OUTDOOR_TEMPERATURE: OUTDOOR_TEMPERATURE,
    CONF_OUTDOOR_HUMIDITY: OUTDOOR_HUMIDITY,
}

# Thresholds in °C (the test instance uses the metric system)
COMFORT: dict[str, Any] = {
    CONF_SIMMER_INDEX_MIN: 21.0,
    CONF_SIMMER_INDEX_MAX: 29.5,
    CONF_DEW_POINT_MAX: 15.5,
    CONF_HUMIDITY_MAX: 95.0,
    CONF_POLLEN_MAX: 2,
    CONF_COOLING_TEMPERATURE_MIN: 15.5,
    CONF_TEMPERATURE_TOLERANCE: 0.5,
}

ENTRY_DATA: dict[str, Any] = {
    **INPUTS,
    **COMFORT,
    CONF_TEMPERATURE_UNIT: UnitOfTemperature.CELSIUS,
    CONF_NAME: "Comfort Advisor",
    CONF_ENABLED_SENSORS: [str(x) for x in Calculated],
}

# (temperature °C, humidity %) samples
NICE = (22.0, 40.0)
HOT = (32.0, 50.0)


class MockWeather(WeatherEntity):
    """Weather entity with a configurable hourly forecast."""

    _attr_name = "Test Weather"
    _attr_native_temperature = 22.0
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_humidity = 40
    _attr_condition = "sunny"
    _attr_supported_features = WeatherEntityFeature.FORECAST_HOURLY

    def __init__(self) -> None:
        """Start with a comfortable day."""
        self.samples: list[tuple[float, float]] = [NICE] * 24
        self.fail = False
        self.include_humidity = True

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        """Return the hourly forecast starting next hour."""
        if self.fail:
            raise HomeAssistantError("forecast unavailable")
        start = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
        return [
            {
                "datetime": (start + timedelta(hours=i + 1)).isoformat(),
                "native_temperature": temp,
                **({"humidity": humidity} if self.include_humidity else {}),
            }
            for i, (temp, humidity) in enumerate(self.samples)
        ]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations in all tests."""
    return


@pytest.fixture
async def weather(hass: HomeAssistant) -> MockWeather:
    """Set up the mock weather entity."""
    return await async_setup_weather(hass)


async def async_setup_weather(hass: HomeAssistant) -> MockWeather:
    """Set up the mock weather entity."""
    entity = MockWeather()
    setup_test_component_platform(hass, WEATHER_DOMAIN, [entity])
    assert await async_setup_component(
        hass, WEATHER_DOMAIN, {WEATHER_DOMAIN: {CONF_PLATFORM: "test"}}
    )
    await hass.async_block_till_done()
    assert hass.states.get(WEATHER_ENTITY)
    return entity


def set_sensors(
    hass: HomeAssistant,
    indoor: tuple[float, float] = (24.0, 50.0),
    outdoor: tuple[float, float] = NICE,
) -> None:
    """Set the input sensor states."""
    for entity_id, value, device_class, unit in (
        (INDOOR_TEMPERATURE, indoor[0], "temperature", UnitOfTemperature.CELSIUS),
        (INDOOR_HUMIDITY, indoor[1], "humidity", PERCENTAGE),
        (OUTDOOR_TEMPERATURE, outdoor[0], "temperature", UnitOfTemperature.CELSIUS),
        (OUTDOOR_HUMIDITY, outdoor[1], "humidity", PERCENTAGE),
    ):
        hass.states.async_set(
            entity_id,
            str(value),
            {ATTR_DEVICE_CLASS: device_class, ATTR_UNIT_OF_MEASUREMENT: unit},
        )


@pytest.fixture
def sensors(hass: HomeAssistant) -> None:
    """Create the input sensors with comfortable values."""
    set_sensors(hass)


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Add a config entry (not yet set up)."""
    entry = MockConfigEntry(
        domain=DOMAIN, data=ENTRY_DATA, title="Comfort Advisor", unique_id="test"
    )
    entry.add_to_hass(hass)
    return entry
