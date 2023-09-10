"""Tests for config flows."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.weather import WeatherEntityFeature
from homeassistant.const import (
    CONF_NAME,
    CONF_TEMPERATURE_UNIT,
    PERCENTAGE,
    TEMP_FAHRENHEIT,
    Platform,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entityfilter import CONF_INCLUDE_ENTITIES
from homeassistant.helpers.selector import selector
from homeassistant.util.unit_conversion import TemperatureConverter as TC
from homeassistant.util.unit_system import METRIC_SYSTEM
import voluptuous as vol

from .comfort import Calculated
from .const import (
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
    CONF_WEATHER,
    DEFAULT_DEWPOINT_MAX,
    DEFAULT_HUMIDITY_MAX,
    DEFAULT_NAME,
    DEFAULT_POLLEN_MAX,
    DEFAULT_SIMMER_INDEX_MAX,
    DEFAULT_SIMMER_INDEX_MIN,
)
from .helpers import domain_entity_ids

ALL_SENSOR_TYPES = [str(x) for x in Calculated]  # type:ignore

VALID_TEMP_UNITS = [
    UnitOfTemperature.CELSIUS,
    UnitOfTemperature.FAHRENHEIT,
]


def build_inputs_schema(hass: HomeAssistant, config: Mapping[str, Any]) -> vol.Schema:
    """Build inputs schema."""
    weather = config.get(CONF_WEATHER, vol.UNDEFINED)
    indoor_temperature = config.get(CONF_INDOOR_TEMPERATURE, vol.UNDEFINED)
    indoor_humidity = config.get(CONF_INDOOR_HUMIDITY, vol.UNDEFINED)
    outdoor_temperature = config.get(CONF_OUTDOOR_TEMPERATURE, vol.UNDEFINED)
    outdoor_humidity = config.get(CONF_OUTDOOR_HUMIDITY, vol.UNDEFINED)

    weather_entity_ids = domain_entity_ids(
        hass, Platform.WEATHER, required_features=WeatherEntityFeature.FORECAST_HOURLY
    )
    temp_sensors = domain_entity_ids(
        hass, Platform.SENSOR, SensorDeviceClass.TEMPERATURE, VALID_TEMP_UNITS
    )
    humidity_sensors = domain_entity_ids(
        hass, Platform.SENSOR, SensorDeviceClass.HUMIDITY, PERCENTAGE
    )

    weather_selector = selector({"entity": {CONF_INCLUDE_ENTITIES: weather_entity_ids}})
    temp_sensor_selector = selector({"entity": {CONF_INCLUDE_ENTITIES: temp_sensors}})
    humidity_sensor_selector = selector({"entity": {CONF_INCLUDE_ENTITIES: humidity_sensors}})

    return vol.Schema(
        {
            vol.Required(CONF_WEATHER, default=weather): weather_selector,
            vol.Required(CONF_INDOOR_TEMPERATURE, default=indoor_temperature): temp_sensor_selector,
            vol.Required(CONF_INDOOR_HUMIDITY, default=indoor_humidity): humidity_sensor_selector,
            vol.Required(
                CONF_OUTDOOR_TEMPERATURE, default=outdoor_temperature
            ): temp_sensor_selector,
            vol.Required(CONF_OUTDOOR_HUMIDITY, default=outdoor_humidity): humidity_sensor_selector,
        }
    )


def build_comfort_schema(hass: HomeAssistant, config: Mapping[str, Any]) -> vol.Schema:
    """Build comfort settings schema."""
    temp_unit = hass.config.units.temperature_unit

    simmer_index_min = config.get(
        CONF_SIMMER_INDEX_MIN,
        round(TC.convert(DEFAULT_SIMMER_INDEX_MIN, TEMP_FAHRENHEIT, temp_unit), 1),
    )
    simmer_index_max = config.get(
        CONF_SIMMER_INDEX_MAX,
        round(TC.convert(DEFAULT_SIMMER_INDEX_MAX, TEMP_FAHRENHEIT, temp_unit), 1),
    )
    dew_point_max = config.get(
        CONF_DEW_POINT_MAX, round(TC.convert(DEFAULT_DEWPOINT_MAX, TEMP_FAHRENHEIT, temp_unit), 1)
    )
    humidity_max = config.get(CONF_HUMIDITY_MAX, DEFAULT_HUMIDITY_MAX)
    pollen_max: int = config.get(CONF_POLLEN_MAX, DEFAULT_POLLEN_MAX)

    temp_step = 0.5 if hass.config.units is METRIC_SYSTEM else 1.0
    temperature_selector = selector(
        {"number": {"mode": "box", "unit_of_measurement": temp_unit, "step": temp_step}}
    )
    humidity_selector = selector(
        {"number": {"mode": "slider", "unit_of_measurement": PERCENTAGE, "min": 90, "max": 100}}
    )

    return vol.Schema(
        {
            vol.Required(CONF_SIMMER_INDEX_MIN, default=simmer_index_min): temperature_selector,  # type: ignore
            vol.Required(CONF_SIMMER_INDEX_MAX, default=simmer_index_max): temperature_selector,  # type: ignore
            vol.Required(CONF_DEW_POINT_MAX, default=dew_point_max): temperature_selector,  # type: ignore
            vol.Required(CONF_HUMIDITY_MAX, default=humidity_max): vol.All(humidity_selector),  # type: ignore
            vol.Required(CONF_POLLEN_MAX, default=pollen_max): vol.In(  # type: ignore
                {0: "none", 1: "very_low", 2: "low", 3: "medium", 4: "high", 5: "very_high"}  # TODO
            ),
        }
    )


def build_device_schema(config: Mapping[str, Any]) -> vol.Schema:
    """Build device settings schema."""
    name: str = config.get(CONF_NAME, DEFAULT_NAME)
    enabled_sensors: Sequence[str] = config.get(CONF_ENABLED_SENSORS, ALL_SENSOR_TYPES)

    all_sensor_types = sorted(ALL_SENSOR_TYPES)
    sensor_type_dict = {x: x.replace("_", " ").title() for x in all_sensor_types}
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=name): str,  # type: ignore
            vol.Required(
                CONF_ENABLED_SENSORS, default=enabled_sensors or all_sensor_types  # type: ignore
            ): cv.multi_select(sensor_type_dict),
        }
    )


DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_WEATHER): cv.entity_id,
        vol.Required(CONF_INDOOR_TEMPERATURE): cv.entity_id,
        vol.Required(CONF_INDOOR_HUMIDITY): cv.entity_id,
        vol.Required(CONF_OUTDOOR_TEMPERATURE): cv.entity_id,
        vol.Required(CONF_OUTDOOR_HUMIDITY): cv.entity_id,
        vol.Required(CONF_SIMMER_INDEX_MIN): vol.Coerce(float),
        vol.Required(CONF_SIMMER_INDEX_MAX): vol.Coerce(float),
        vol.Required(CONF_DEW_POINT_MAX): vol.Coerce(float),
        vol.Required(CONF_HUMIDITY_MAX): vol.Coerce(float),
        vol.Required(CONF_POLLEN_MAX): vol.All(vol.Coerce(int), vol.Range(min=0, max=5)),
        vol.Required(CONF_TEMPERATURE_UNIT): vol.In(VALID_TEMP_UNITS),
        vol.Required(CONF_NAME): vol.All(str, vol.Length(min=1)),
        vol.Required(CONF_ENABLED_SENSORS): cv.multi_select(ALL_SENSOR_TYPES),
    }
)
