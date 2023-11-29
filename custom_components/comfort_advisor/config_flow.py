"""Tests for config flows."""
from __future__ import annotations

from hashlib import md5
from typing import Any, Iterable, Mapping, MutableMapping

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_NAME,
    CONF_TEMPERATURE_UNIT,
    PERCENTAGE,
    TEMP_FAHRENHEIT,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import entity_registry
from homeassistant.helpers.typing import ConfigType
from homeassistant.util.unit_conversion import TemperatureConverter as TC
import voluptuous as vol

from .const import (
    CONF_INDOOR_HUMIDITY,
    CONF_INDOOR_TEMPERATURE,
    CONF_OUTDOOR_HUMIDITY,
    CONF_OUTDOOR_TEMPERATURE,
    CONF_WEATHER,
    DOMAIN,
)
from .schemas import DATA_SCHEMA, build_comfort_schema, build_device_schema, build_inputs_schema

ErrorsType = MutableMapping[str, str]


def _validate_inputs(
    hass: HomeAssistant,
    errors: ErrorsType,
    /,
    indoor_temperature: str,
    indoor_humidity: str,
    outdoor_temperature: str,
    outdoor_humidity: str,
) -> bool:
    def validate_sensor_units(entity_ids: Iterable[str], valid_units: Iterable[str | None]) -> bool:
        for entity_id in entity_ids:
            state = hass.states.get(entity_id)
            if not state:
                errors["base"] = "sensor_entity"
                errors["sensor"] = entity_id
                return False

            unit: str | None = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
            if not unit or unit not in valid_units:
                errors["base"] = "sensor_units"
                errors["sensor"] = state.name
                return False
        return True

    return validate_sensor_units(
        [indoor_temperature, outdoor_temperature], TC.VALID_UNITS
    ) and validate_sensor_units([indoor_humidity, outdoor_humidity], [PERCENTAGE])


def _create_unique_id(hass: HomeAssistant, inputs_config: ConfigType) -> str:
    ent_reg = entity_registry.async_get(hass)
    values: list[str] = []
    for key in (
        CONF_INDOOR_TEMPERATURE,
        CONF_INDOOR_HUMIDITY,
        CONF_OUTDOOR_TEMPERATURE,
        CONF_OUTDOOR_HUMIDITY,
        CONF_WEATHER,
    ):
        entity_id: str = inputs_config[key]
        entity = ent_reg.async_get(entity_id)
        values.append(entity.unique_id if entity else entity_id)

    return md5(str(values).encode("utf8")).hexdigest()


def _build_comfort_placeholders(temp_unit: str) -> Mapping[str, Any]:
    return {str(x): round(TC.convert(x, TEMP_FAHRENHEIT, temp_unit), 1) for x in (70, 77, 83, 91)}


class ComfortAdvisorConfigFlow(ConfigFlow, domain=DOMAIN):  # type: ignore
    """Configuration flow for setting up new comfort_advisor entry."""

    def __init__(self) -> None:
        """Initialize config flow."""

        self._config: dict[str, Any] = {}
        self._weather_schema: vol.Schema | None = None

    async def async_step_user(self, user_input: ConfigType | None = None) -> FlowResult:
        """Select temperature and humidity sensors."""
        user_input = user_input or {}
        errors: ErrorsType = {}

        if user_input:
            if (
                user_input[CONF_INDOOR_TEMPERATURE] == user_input[CONF_OUTDOOR_TEMPERATURE]
                or user_input[CONF_INDOOR_HUMIDITY] == user_input[CONF_OUTDOOR_HUMIDITY]
            ):
                errors["base"] = "sensors_not_unique"
            else:
                unique_id = _create_unique_id(self.hass, user_input)
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                # if _validate_inputs(self.hass, errors, **user_input):
                self._config.update(user_input)
                return await self.async_step_comfort()

        schema = await build_inputs_schema(self.hass, user_input)

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_comfort(self, user_input: ConfigType | None = None) -> FlowResult:
        """Adjust comfort values."""
        user_input = user_input or {}
        errors: ErrorsType = {}

        temp_unit = self.hass.config.units.temperature_unit

        if user_input:
            self._config.update(user_input)
            self._config[CONF_TEMPERATURE_UNIT] = temp_unit
            return await self.async_step_device()

        schema = build_comfort_schema(self.hass, user_input)
        placeholders = _build_comfort_placeholders(temp_unit)

        return self.async_show_form(
            step_id="comfort",
            data_schema=schema,
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_device(self, user_input: ConfigType | None = None) -> FlowResult:
        """Adjust device settings."""
        user_input = user_input or {}
        errors: ErrorsType = {}

        if user_input:
            self._config.update(user_input)
            config = DATA_SCHEMA(self._config)
            return self.async_create_entry(title=user_input[CONF_NAME], data=config)

        schema = build_device_schema(user_input)

        return self.async_show_form(step_id="device", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return ComfortAdvisorOptionsFlow(config_entry)


class ComfortAdvisorOptionsFlow(OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry: ConfigEntry):
        """Initialize options flow."""
        self._original = config_entry.data | config_entry.options
        self._config: dict[str, Any] = {}

    async def async_step_init(self, user_input: ConfigType | None = None) -> FlowResult:
        """Adjust comfort values."""
        user_input = user_input or {}
        errors: ErrorsType = {}

        if user_input:
            self._config.update(user_input)
            return await self.async_step_device()

        temp_unit = self.hass.config.units.temperature_unit

        schema = build_comfort_schema(self.hass, self._original)
        placeholders = _build_comfort_placeholders(temp_unit)

        return self.async_show_form(
            step_id="init", errors=errors, data_schema=schema, description_placeholders=placeholders
        )

    async def async_step_device(self, user_input: ConfigType | None = None) -> FlowResult:
        """Adjust device settings."""
        user_input = user_input or {}
        errors: ErrorsType = {}

        if user_input:
            self._config.update(user_input)
            return self.async_create_entry(title=user_input[CONF_NAME], data=self._config)

        schema = build_device_schema(self._original)

        return self.async_show_form(step_id="device", data_schema=schema, errors=errors)
