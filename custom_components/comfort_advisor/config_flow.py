"""Tests for config flows."""
from __future__ import annotations

from hashlib import md5
from types import ModuleType
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_NAME,
    PERCENTAGE,
    TEMP_FAHRENHEIT,
)
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import entity_registry
from homeassistant.helpers.typing import ConfigType
from homeassistant.requirements import RequirementsNotFound
from homeassistant.util.temperature import (
    VALID_UNITS as TEMPERATURE_UNITS,
    convert as convert_temp,
)
import voluptuous as vol

from .const import (
    CONF_COMFORT,
    CONF_DEVICE,
    CONF_INDOOR_HUMIDITY,
    CONF_INDOOR_TEMPERATURE,
    CONF_INPUTS,
    CONF_OUTDOOR_HUMIDITY,
    CONF_OUTDOOR_TEMPERATURE,
    CONF_PROVIDER,
    CONF_PROVIDER_TYPE,
    DOMAIN,
    PROVIDER_TYPES,
)
from .helpers import create_issue_tracker_url, load_module
from .provider import PROVIDERS, ProviderError
from .schemas import (
    build_comfort_schema,
    build_device_schema,
    build_inputs_schema,
    build_provider_schema,
)

ErrorsType = dict[str, str]


async def _async_test_provider(
    hass: HomeAssistant, errors: ErrorsType, provider_type: str, **kwargs: dict[str, Any]
) -> bool:
    factory = PROVIDERS.get(provider_type)
    provider = factory(hass, **kwargs)
    try:
        await provider.realtime()
        return True
    except ProviderError as exc:
        errors["base"] = exc.error_key
        return False


def _async_test_inputs(
    hass: HomeAssistant,
    errors: ErrorsType,
    *,
    indoor_temperature: str,
    indoor_humidity: str,
    outdoor_temperature: str,
    outdoor_humidity: str,
) -> bool:
    def check_sensor_units(entity_ids: list[str], valid_units: list[str]) -> bool:
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


class ComfortAdvisorConfigFlow(ConfigFlow, domain=DOMAIN):  # type: ignore
    """Configuration flow for setting up new comfort_advisor entry."""

    def __init__(self) -> None:
        """TODO."""

        self._config: dict[str, Any] = {}
        self._provider_type: str | None = None
        self._provider_module: ModuleType | None = None

        self._provider_config: dict[str, Any] | None = None
        self._inputs_config: dict[str, Any] | None = None
        self._comfort_config: dict[str, Any] | None = None

    async def async_step_user(self, user_input: ConfigType | None = None) -> FlowResult:
        """Handle a flow initialized by the user. Choose a provider."""
        user_input = user_input or {}

        if len(PROVIDER_TYPES) == 1:
            user_input = {CONF_PROVIDER_TYPE: list(PROVIDER_TYPES.keys())[0]}

        if user_input:
            self._provider_type = user_input[CONF_PROVIDER_TYPE]
            return await self.async_step_provider()

        schema = build_provider_schema()

        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_provider(self, user_input: ConfigType | None = None) -> FlowResult:
        """Enter provider configuration."""
        user_input = user_input or {}
        errors: ErrorsType = {}

        assert self._provider_type is not None
        default_provider_config = {CONF_PROVIDER_TYPE: self._provider_type}

        if user_input:
            if await _async_test_provider(self.hass, errors, self._provider_type, **user_input):
                self._provider_config = {**default_provider_config, **user_input}
                return await self.async_step_inputs()

        if self._provider_module is None:
            try:
                self._provider_module = await load_module(self.hass, self._provider_type)
            except (ImportError, RequirementsNotFound) as exc:
                issue_url = await create_issue_tracker_url(
                    self.hass, exc, title=f"Error loading '{self._provider_type}' provider"
                )
                return self.async_abort(
                    reason="load_provider",
                    description_placeholders={
                        "provider": self._provider_type,
                        "message": getattr(exc, "msg"),
                        "issue_url": issue_url,
                    },
                )

        schema: vol.Schema = self._provider_module.build_schema(self.hass, **user_input)
        if not schema.schema:
            self._provider_config = default_provider_config
            return await self.async_step_inputs()

        return self.async_show_form(
            step_id="provider",
            errors=errors,
            data_schema=schema,
            description_placeholders={
                "provider_desc": getattr(self._provider_module, "DESCRIPTION", None)
            },
        )

    async def async_step_inputs(self, user_input: ConfigType | None = None) -> FlowResult:
        """Select temperature and humidity sensors."""
        user_input = user_input or {}
        errors: ErrorsType = {}

        if user_input:
            if _async_test_inputs(self.hass, errors, **user_input):  # pylint: disable=missing-kwoa
                self._inputs_config = user_input
                return await self.async_step_comfort()

        return self.async_show_form(
            step_id="inputs",
            errors=errors,
            data_schema=build_inputs_schema(**user_input),
        )

    async def async_step_comfort(self, user_input: ConfigType | None = None) -> FlowResult:
        """Adjust comfort values."""
        user_input = user_input or {}
        errors: ErrorsType = {}

        if user_input:
            self._comfort_config = user_input
            return await self.async_step_device()

        temp_unit = self.hass.config.units.temperature_unit
        description_placeholders = {
            str(x): round(convert_temp(x, TEMP_FAHRENHEIT, temp_unit), 1) for x in (70, 77, 83, 91)
        }

        return self.async_show_form(
            step_id="comfort",
            errors=errors,
            data_schema=build_comfort_schema(self.hass, **user_input),
            description_placeholders=description_placeholders,
        )

    async def async_step_device(self, user_input: ConfigType | None = None) -> FlowResult:
        """TODO."""
        user_input = user_input or {}
        errors: ErrorsType = {}

        if user_input:
            config = {
                CONF_PROVIDER: self._provider_config,
                CONF_INPUTS: self._inputs_config,
                CONF_COMFORT: self._comfort_config,
                CONF_DEVICE: user_input,
            }
            unique_id = _create_unique_id(self.hass, self._inputs_config)
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=user_input[CONF_NAME], data=config)

        return self.async_show_form(
            step_id="device",
            errors=errors,
            data_schema=build_device_schema(**user_input),
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
        self.config_entry = config_entry
        self._comfort_config: dict[str, Any] | None = None

    async def async_step_init(self, user_input: ConfigType = None) -> FlowResult:
        """Manage the options."""
        user_input = user_input or {}
        errors: ErrorsType = {}

        if user_input:
            self._comfort_config = user_input
            return await self.async_step_device()

        temp_unit = self.hass.config.units.temperature_unit
        description_placeholders = {
            str(x): round(convert_temp(x, TEMP_FAHRENHEIT, temp_unit), 1) for x in (70, 77, 83, 91)
        }

        return self.async_show_form(
            step_id="init",
            errors=errors,
            data_schema=build_comfort_schema(self.hass, **user_input),
            description_placeholders=description_placeholders,
        )

    async def async_step_device(self, user_input: ConfigType | None = None) -> FlowResult:
        """TODO."""
        user_input = user_input or {}
        errors: ErrorsType = {}

        if user_input:
            config = {
                CONF_COMFORT: self._comfort_config,
                CONF_DEVICE: user_input,
            }
            return self.async_create_entry(title=user_input[CONF_NAME], data=config)

        return self.async_show_form(
            step_id="device",
            errors=errors,
            data_schema=build_device_schema(**user_input),
        )
