"""Tests for config flows."""
from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_NAME, TEMP_FAHRENHEIT
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import selector
from homeassistant.util.temperature import convert as convert_temp
import voluptuous as vol

from .const import (
    ALL_BINARY_SENSOR_TYPES,
    ALL_SENSOR_TYPES,
    CONF_COMFORT,
    CONF_DEVICE,
    CONF_DEWPOINT_MAX,
    CONF_ENABLED_SENSORS,
    CONF_HUMIDITY_MAX,
    CONF_INDOOR_HUMIDITY,
    CONF_INDOOR_TEMPERATURE,
    CONF_INPUTS,
    CONF_OUTDOOR_HUMIDITY,
    CONF_OUTDOOR_TEMPERATURE,
    CONF_POLL,
    CONF_POLL_INTERVAL,
    CONF_POLLEN_MAX,
    CONF_PROVIDER,
    CONF_PROVIDER_TYPE,
    CONF_SIMMER_INDEX_MAX,
    CONF_SIMMER_INDEX_MIN,
    DEFAULT_DEWPOINT_MAX,
    DEFAULT_HUMIDITY_MAX,
    DEFAULT_NAME,
    DEFAULT_POLL,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_POLLEN_MAX,
    DEFAULT_SIMMER_INDEX_MAX,
    DEFAULT_SIMMER_INDEX_MIN,
    PROVIDER_TYPES,
)
from .helpers import HUMIDITY_SENSOR_SELECTOR, TEMP_SENSOR_SELECTOR


def value_or_default(value: Any, default: Any) -> Any:
    """TODO."""
    return default if value is vol.UNDEFINED else value


def build_provider_schema() -> vol.Schema:
    """TODO."""
    return vol.Schema(
        {vol.Required(CONF_PROVIDER_TYPE): vol.In(PROVIDER_TYPES)},
        extra=vol.ALLOW_EXTRA,
    )


def build_inputs_schema(
    *,
    indoor_temp: float = vol.UNDEFINED,
    indoor_humidity: float = vol.UNDEFINED,
    outdoor_temp: float = vol.UNDEFINED,
    outdoor_humidity: float = vol.UNDEFINED,
) -> vol.Schema:
    """TODO."""
    return vol.Schema(
        {
            vol.Required(CONF_INDOOR_TEMPERATURE, default=indoor_temp): TEMP_SENSOR_SELECTOR,
            vol.Required(CONF_INDOOR_HUMIDITY, default=indoor_humidity): HUMIDITY_SENSOR_SELECTOR,
            vol.Required(CONF_OUTDOOR_TEMPERATURE, default=outdoor_temp): TEMP_SENSOR_SELECTOR,
            vol.Required(CONF_OUTDOOR_HUMIDITY, default=outdoor_humidity): HUMIDITY_SENSOR_SELECTOR,
        }
    )


def build_comfort_schema(
    hass: HomeAssistant,
    *,
    simmer_index_min: float = vol.UNDEFINED,
    simmer_index_max: float = vol.UNDEFINED,
    dew_point_max: float = vol.UNDEFINED,
    humidity_max: float = vol.UNDEFINED,
    pollen_max: int = vol.UNDEFINED,
) -> vol.Schema:
    """TODO."""
    temp_unit = hass.config.units.temperature_unit

    # TODO: round to nearest 0.5?
    dewp_max_default = round(convert_temp(DEFAULT_DEWPOINT_MAX, TEMP_FAHRENHEIT, temp_unit), 1)
    si_max_default = round(convert_temp(DEFAULT_SIMMER_INDEX_MAX, TEMP_FAHRENHEIT, temp_unit), 1)
    si_min_default = round(convert_temp(DEFAULT_SIMMER_INDEX_MIN, TEMP_FAHRENHEIT, temp_unit), 1)

    temperature_selector = selector({"number": {"mode": "box", "unit_of_measurement": temp_unit}})
    humidity_selector = selector(
        {"number": {"mode": "slider", "unit_of_measurement": "%", "min": 90, "max": 100}}
    )

    return vol.Schema(
        {
            vol.Required(
                CONF_SIMMER_INDEX_MIN, default=value_or_default(simmer_index_min, si_min_default)
            ): temperature_selector,
            vol.Required(
                CONF_SIMMER_INDEX_MAX, default=value_or_default(simmer_index_max, si_max_default)
            ): temperature_selector,
            vol.Required(
                CONF_DEWPOINT_MAX, default=value_or_default(dew_point_max, dewp_max_default)
            ): temperature_selector,
            vol.Required(
                CONF_HUMIDITY_MAX, default=value_or_default(humidity_max, DEFAULT_HUMIDITY_MAX)
            ): vol.All(humidity_selector),
            vol.Required(
                CONF_POLLEN_MAX, default=value_or_default(pollen_max, DEFAULT_POLLEN_MAX)
            ): vol.In(
                {0: "none", 1: "very_low", 2: "low", 3: "medium", 4: "high", 5: "very_high"}  # TODO
            ),
        }
    )


def build_device_schema(
    *,
    name: str = vol.UNDEFINED,
    enabled_sensors: list[str] = vol.UNDEFINED,
    poll: bool = vol.UNDEFINED,
    poll_interval: int = vol.UNDEFINED,
) -> vol.Schema:
    """TODO."""
    all_sensor_types = sorted(ALL_BINARY_SENSOR_TYPES + ALL_SENSOR_TYPES)
    sensor_type_dict = {x: x.replace("_", " ").title() for x in all_sensor_types}
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=value_or_default(name, DEFAULT_NAME)): str,
            vol.Optional(
                CONF_ENABLED_SENSORS, default=value_or_default(enabled_sensors, all_sensor_types)
            ): cv.multi_select(sensor_type_dict),
            vol.Optional(CONF_POLL, default=value_or_default(poll, DEFAULT_POLL)): bool,
            vol.Optional(
                CONF_POLL_INTERVAL, default=value_or_default(poll_interval, DEFAULT_POLL_INTERVAL)
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=300)),
        }
    )


def build_schema(hass: HomeAssistant) -> vol.Schema:
    """TODO."""
    return vol.Schema(
        {
            vol.Required(CONF_PROVIDER): build_provider_schema().schema,
            vol.Required(CONF_INPUTS): build_inputs_schema().schema,
            vol.Required(CONF_COMFORT): build_comfort_schema(hass).schema,
            vol.Required(CONF_DEVICE): build_device_schema().schema,
        }
    )
