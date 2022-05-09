"""Tests for config flows."""
from __future__ import annotations

from hashlib import md5
from types import ModuleType
from typing import Any, Iterable, Mapping, MutableMapping

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_NAME,
    CONF_TEMPERATURE_UNIT,
    PERCENTAGE,
    TEMP_FAHRENHEIT,
)
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import entity_registry
from homeassistant.helpers.typing import ConfigType
from homeassistant.requirements import RequirementsNotFound
from homeassistant.util.temperature import VALID_UNITS as TEMPERATURE_UNITS
from homeassistant.util.temperature import convert as convert_temp
import voluptuous as vol

from .const import (
    CONF_INDOOR_HUMIDITY,
    CONF_INDOOR_TEMPERATURE,
    CONF_OUTDOOR_HUMIDITY,
    CONF_OUTDOOR_TEMPERATURE,
    CONF_PROVIDER,
    CONF_WEATHER,
    DOMAIN,
    PROVIDER_TYPES,
)
from .helpers import create_issue_tracker_url, load_module
from .provider import PROVIDERS, ProviderError
from .schemas import (
    DATA_SCHEMA,
    build_comfort_schema,
    build_device_schema,
    build_inputs_schema,
    build_weather_schema,
)

ErrorsType = MutableMapping[str, str]


async def _async_test_weather(
    hass: HomeAssistant, errors: ErrorsType, provider_config: Mapping[str, Any]
) -> bool:
    provider_type: str = provider_config[CONF_PROVIDER]
    provider_factory = PROVIDERS.get(provider_type)
    provider = provider_factory(hass, provider_config)
    try:
        await provider.fetch_realtime()
        return True
    except ProviderError as exc:
        errors["base"] = exc.error_key
        return False


def _async_test_inputs(
    hass: HomeAssistant,
    errors: ErrorsType,
    /,
    indoor_temperature: str,
    indoor_humidity: str,
    outdoor_temperature: str,
    outdoor_humidity: str,
) -> bool:
    def check_sensor_units(entity_ids: Iterable[str], valid_units: Iterable[str]) -> bool:
        for entity_id in entity_ids:
            state: State = hass.states.get(entity_id)
            unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
            if unit not in valid_units:
                errors["base"] = "sensor_units"
                errors["sensor"] = state.name
                return False
        return True

    return check_sensor_units(
        [indoor_temperature, outdoor_temperature], TEMPERATURE_UNITS
    ) and check_sensor_units([indoor_humidity, outdoor_humidity], [PERCENTAGE])


def _create_unique_id(hass: HomeAssistant, inputs_config: ConfigType) -> str:
    ent_reg = entity_registry.async_get(hass)
    values = [
        ent_reg.async_get(inputs_config[key]).unique_id
        for key in (
            CONF_INDOOR_TEMPERATURE,
            CONF_INDOOR_HUMIDITY,
            CONF_OUTDOOR_TEMPERATURE,
            CONF_OUTDOOR_HUMIDITY,
        )
    ]
    return md5(str(values).encode("utf8")).hexdigest()


def _build_comfort_placeholders(temp_unit: str) -> Mapping[str, Any]:
    return {str(x): round(convert_temp(x, TEMP_FAHRENHEIT, temp_unit), 1) for x in (70, 77, 83, 91)}


class ComfortAdvisorConfigFlow(ConfigFlow, domain=DOMAIN):  # type: ignore
    """Configuration flow for setting up new comfort_advisor entry."""

    def __init__(self) -> None:
        """Initialize config flow."""

        self._config: dict[str, Any] = {}
        self._weather_module: ModuleType | None = None
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

                if _async_test_inputs(self.hass, errors, **user_input):
                    self._config.update(user_input)
                    return await self.async_step_choose()

        return self.async_show_form(
            step_id="user",
            errors=errors,
            data_schema=build_inputs_schema(self.hass, user_input),
        )

    async def async_step_choose(self, user_input: ConfigType | None = None) -> FlowResult:
        """Handle a flow initialized by the user. Choose a weather provider."""
        user_input = user_input or {}

        if len(PROVIDER_TYPES) == 1:
            user_input = {CONF_PROVIDER: list(PROVIDER_TYPES.keys())[0]}

        if user_input:
            self._config[CONF_WEATHER] = user_input
            return await self.async_step_weather()

        return self.async_show_form(
            step_id="choose", data_schema=build_weather_schema(self.hass, user_input)
        )

    async def async_step_weather(self, user_input: ConfigType | None = None) -> FlowResult:
        """Enter weather provider configuration."""
        user_input = user_input or {}
        errors: ErrorsType = {}
        weather_config = self._config[CONF_WEATHER]

        if self._weather_module is None:
            provider_type = weather_config[CONF_PROVIDER]
            try:
                self._weather_module = await load_module(self.hass, provider_type)
            except (ImportError, RequirementsNotFound) as exc:
                issue_url = await create_issue_tracker_url(
                    self.hass, exc, title=f"Error loading '{provider_type}' provider"
                )
                placeholders = {
                    "provider": provider_type,
                    "message": getattr(exc, "msg"),
                    "issue_url": issue_url,
                }
                return self.async_abort(
                    reason="load_provider", description_placeholders=placeholders
                )

        weather_config = {**weather_config, **user_input}

        if not self._weather_schema:
            self._weather_schema = build_weather_schema(self.hass, weather_config)

        if user_input or not self._weather_schema.schema:
            if await _async_test_weather(self.hass, errors, weather_config):
                self._config[CONF_WEATHER] = weather_config
                return await self.async_step_comfort()

        placeholders = {"provider_desc": getattr(self._weather_module, "DESCRIPTION", None)}

        return self.async_show_form(
            step_id="weather",
            errors=errors,
            data_schema=self._weather_schema,
            description_placeholders=placeholders,
        )

    async def async_step_comfort(self, user_input: ConfigType | None = None) -> FlowResult:
        """Adjust comfort values."""
        user_input = user_input or {}
        errors: ErrorsType = {}

        temp_unit = self.hass.config.units.temperature_unit

        if user_input:
            self._config.update(user_input)
            self._config[CONF_TEMPERATURE_UNIT] = temp_unit
            return await self.async_step_device()

        return self.async_show_form(
            step_id="comfort",
            errors=errors,
            data_schema=build_comfort_schema(self.hass, user_input),
            description_placeholders=_build_comfort_placeholders(temp_unit),
        )

    async def async_step_device(self, user_input: ConfigType | None = None) -> FlowResult:
        """Adjust device settings."""
        user_input = user_input or {}
        errors: ErrorsType = {}

        if user_input:
            self._config.update(user_input)
            config = DATA_SCHEMA(self._config)
            return self.async_create_entry(title=user_input[CONF_NAME], data=config)

        return self.async_show_form(
            step_id="device",
            errors=errors,
            data_schema=build_device_schema(user_input),
        )

    @staticmethod
    @callback  # type: ignore
    def async_get_options_flow(config_entry: ConfigEntry) -> ConfigFlow:
        """Get the options flow for this handler."""
        return ComfortAdvisorOptionsFlow(config_entry)


class ComfortAdvisorOptionsFlow(OptionsFlow):  # type: ignore
    """Handle options."""

    def __init__(self, config_entry: ConfigEntry):
        """Initialize options flow."""
        self._original = config_entry.data | config_entry.options
        self._config: dict[str, Any] = {}

    async def async_step_init(self, user_input: ConfigType = None) -> FlowResult:
        """Adjust comfort values."""
        user_input = user_input or {}
        errors: ErrorsType = {}

        if user_input:
            self._config.update(user_input)
            return await self.async_step_device()

        temp_unit = self.hass.config.units.temperature_unit

        return self.async_show_form(
            step_id="init",
            errors=errors,
            data_schema=build_comfort_schema(self.hass, self._original),
            description_placeholders=_build_comfort_placeholders(temp_unit),
        )

    async def async_step_device(self, user_input: ConfigType | None = None) -> FlowResult:
        """Adjust device settings."""
        user_input = user_input or {}
        errors: ErrorsType = {}

        if user_input:
            self._config.update(user_input)
            return self.async_create_entry(title=user_input[CONF_NAME], data=self._config)

        return self.async_show_form(
            step_id="device",
            errors=errors,
            data_schema=build_device_schema(self._original),
        )
