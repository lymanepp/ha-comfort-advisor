"""Tests for config flows."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import (
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LOCATION,
    CONF_LONGITUDE,
    CONF_NAME,
    CONF_TEMPERATURE_UNIT,
    PERCENTAGE,
    TEMP_FAHRENHEIT,
)
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entityfilter import CONF_INCLUDE_ENTITIES
from homeassistant.helpers.selector import selector
from homeassistant.util.temperature import VALID_UNITS as VALID_TEMP_UNITS
from homeassistant.util.temperature import convert as convert_temp
import voluptuous as vol

from .comfort import State
from .const import (
    CONF_DEW_POINT_MAX,
    CONF_ENABLED_SENSORS,
    CONF_HUMIDITY_MAX,
    CONF_INDOOR_HUMIDITY,
    CONF_INDOOR_TEMPERATURE,
    CONF_OUTDOOR_HUMIDITY,
    CONF_OUTDOOR_TEMPERATURE,
    CONF_POLLEN_MAX,
    CONF_PROVIDER,
    CONF_SIMMER_INDEX_MAX,
    CONF_SIMMER_INDEX_MIN,
    CONF_WEATHER,
    DEFAULT_DEWPOINT_MAX,
    DEFAULT_HUMIDITY_MAX,
    DEFAULT_NAME,
    DEFAULT_POLLEN_MAX,
    DEFAULT_SIMMER_INDEX_MAX,
    DEFAULT_SIMMER_INDEX_MIN,
    PROVIDER_TYPES,
)
from .helpers import get_sensor_entities

ALL_SENSOR_TYPES = [str(x) for x in State]  # type:ignore


def build_weather_schema(hass: HomeAssistant, weather_config: Mapping[str, Any]) -> vol.Schema:
    """Build provider schema."""
    provider_type: str = weather_config.get(CONF_PROVIDER, vol.UNDEFINED)

    if provider_type == vol.UNDEFINED:
        return vol.Schema(
            {vol.Required(CONF_PROVIDER): vol.In(PROVIDER_TYPES)},
        )

    default_location = {CONF_LATITUDE: hass.config.latitude, CONF_LONGITUDE: hass.config.longitude}

    api_key: str = weather_config.get(CONF_API_KEY, vol.UNDEFINED)
    location: Mapping[str, float] = weather_config.get(CONF_LOCATION, default_location)

    return vol.Schema(
        {
            vol.Required(CONF_API_KEY, default=api_key): vol.All(str, vol.Length(min=1)),
            vol.Required(CONF_LOCATION, default=location): selector(
                {"location": {"radius": False}}
            ),
        }
    )


def build_inputs_schema(hass: HomeAssistant, config: Mapping[str, Any]) -> vol.Schema:
    """Build inputs schema."""
    indoor_temperature: float = config.get(CONF_INDOOR_TEMPERATURE, vol.UNDEFINED)
    indoor_humidity: float = config.get(CONF_INDOOR_HUMIDITY, vol.UNDEFINED)
    outdoor_temperature: float = config.get(CONF_OUTDOOR_TEMPERATURE, vol.UNDEFINED)
    outdoor_humidity: float = config.get(CONF_OUTDOOR_HUMIDITY, vol.UNDEFINED)

    temp_sensors = get_sensor_entities(hass, SensorDeviceClass.TEMPERATURE, VALID_TEMP_UNITS)
    humidity_sensors = get_sensor_entities(hass, SensorDeviceClass.HUMIDITY, [PERCENTAGE])

    temp_sensor_selector = selector({"entity": {CONF_INCLUDE_ENTITIES: temp_sensors}})
    humidity_sensor_selector = selector({"entity": {CONF_INCLUDE_ENTITIES: humidity_sensors}})

    return vol.Schema(
        {
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

    simmer_index_min: float = config.get(
        CONF_SIMMER_INDEX_MIN,
        round(convert_temp(DEFAULT_SIMMER_INDEX_MIN, TEMP_FAHRENHEIT, temp_unit), 1),
    )
    simmer_index_max: float = config.get(
        CONF_SIMMER_INDEX_MAX,
        round(convert_temp(DEFAULT_SIMMER_INDEX_MAX, TEMP_FAHRENHEIT, temp_unit), 1),
    )
    dew_point_max: float = config.get(
        CONF_DEW_POINT_MAX, round(convert_temp(DEFAULT_DEWPOINT_MAX, TEMP_FAHRENHEIT, temp_unit), 1)
    )
    humidity_max: float = config.get(CONF_HUMIDITY_MAX, DEFAULT_HUMIDITY_MAX)
    pollen_max: int = config.get(CONF_POLLEN_MAX, DEFAULT_POLLEN_MAX)

    temp_step = 0.5 if hass.config.units.is_metric else 1.0
    temperature_selector = selector(
        {"number": {"mode": "box", "unit_of_measurement": temp_unit, "step": temp_step}}
    )
    humidity_selector = selector(
        {"number": {"mode": "slider", "unit_of_measurement": PERCENTAGE, "min": 90, "max": 100}}
    )

    return vol.Schema(
        {
            vol.Required(CONF_SIMMER_INDEX_MIN, default=simmer_index_min): temperature_selector,
            vol.Required(CONF_SIMMER_INDEX_MAX, default=simmer_index_max): temperature_selector,
            vol.Required(CONF_DEW_POINT_MAX, default=dew_point_max): temperature_selector,
            vol.Required(CONF_HUMIDITY_MAX, default=humidity_max): vol.All(humidity_selector),
            vol.Required(CONF_POLLEN_MAX, default=pollen_max): vol.In(
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
            vol.Required(CONF_NAME, default=name): str,
            vol.Required(
                CONF_ENABLED_SENSORS, default=enabled_sensors or all_sensor_types
            ): cv.multi_select(sensor_type_dict),
        }
    )


_API_KEY_AND_LOCATION = {
    vol.Required(CONF_API_KEY): vol.All(str, vol.Length(min=1)),
    vol.Required(CONF_LOCATION): {
        vol.Required(CONF_LATITUDE): cv.latitude,
        vol.Required(CONF_LONGITUDE): cv.longitude,
    },
}

_WEATHER_SCHEMA = cv.key_value_schemas(
    CONF_PROVIDER,
    {
        "nws": vol.Schema({vol.Required(CONF_PROVIDER): "nws", **_API_KEY_AND_LOCATION}),
        "tomorrowio": vol.Schema(
            {vol.Required(CONF_PROVIDER): "tomorrowio", **_API_KEY_AND_LOCATION}
        ),
    },
)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_INDOOR_TEMPERATURE): cv.entity_id,
        vol.Required(CONF_INDOOR_HUMIDITY): cv.entity_id,
        vol.Required(CONF_OUTDOOR_TEMPERATURE): cv.entity_id,
        vol.Required(CONF_OUTDOOR_HUMIDITY): cv.entity_id,
        vol.Required(CONF_WEATHER): _WEATHER_SCHEMA,
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
