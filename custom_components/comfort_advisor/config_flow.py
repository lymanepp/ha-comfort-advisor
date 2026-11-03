"""Config and options flows for comfort_advisor."""

from collections.abc import Collection, Mapping
from hashlib import md5
from typing import Any, Final

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_NAME,
    CONF_TEMPERATURE_UNIT,
    PERCENTAGE,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry
from homeassistant.helpers.typing import ConfigType
from homeassistant.util.unit_conversion import TemperatureConverter as TC

from .const import (
    CONF_INDOOR_HUMIDITY,
    CONF_INDOOR_TEMPERATURE,
    CONF_OUTDOOR_HUMIDITY,
    CONF_OUTDOOR_TEMPERATURE,
    CONF_WEATHER,
    DOMAIN,
)
from .schemas import DATA_SCHEMA, build_comfort_schema, build_device_schema, build_inputs_schema

type ErrorsType = dict[str, str]


INPUT_UNITS: Final[dict[str, Collection[str | None]]] = {
    CONF_INDOOR_TEMPERATURE: TC.VALID_UNITS,
    CONF_INDOOR_HUMIDITY: (PERCENTAGE,),
    CONF_OUTDOOR_TEMPERATURE: TC.VALID_UNITS,
    CONF_OUTDOOR_HUMIDITY: (PERCENTAGE,),
}


def _validate_inputs(hass: HomeAssistant, user_input: Mapping[str, Any]) -> ErrorsType:
    """Check the selected entities; return errors keyed by field."""
    errors: ErrorsType = {}

    if (
        user_input[CONF_INDOOR_TEMPERATURE] == user_input[CONF_OUTDOOR_TEMPERATURE]
        or user_input[CONF_INDOOR_HUMIDITY] == user_input[CONF_OUTDOOR_HUMIDITY]
    ):
        errors["base"] = "sensors_not_unique"

    if hass.states.get(user_input[CONF_WEATHER]) is None:
        errors[CONF_WEATHER] = "entity_not_found"

    for key, valid_units in INPUT_UNITS.items():
        state = hass.states.get(user_input[key])
        if state is None:
            errors[key] = "entity_not_found"
        elif state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) not in valid_units:
            errors[key] = "invalid_units"

    return errors


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


def _build_comfort_placeholders(temp_unit: str) -> dict[str, str]:
    return {
        "simmer_index_url": "http://summersimmer.com/home.htm",
        "dew_point_url": (
            "https://weatherology.com/trending/articles/"
            "Professor-Paul-Dew-Point-Relative-Humidity.html"
        ),
    } | {
        f"ssi_{x}": str(round(TC.convert(x, UnitOfTemperature.FAHRENHEIT, temp_unit), 1))
        for x in (70, 77, 83, 91)
    }


class ComfortAdvisorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configuration flow for setting up new comfort_advisor entry."""

    def __init__(self) -> None:
        """Initialize config flow."""

        self._config: dict[str, Any] = {}

    async def async_step_user(self, user_input: ConfigType | None = None) -> ConfigFlowResult:
        """Select temperature and humidity sensors."""
        user_input = user_input or {}
        errors: ErrorsType = {}

        if user_input:
            errors = _validate_inputs(self.hass, user_input)
            if not errors:
                unique_id = _create_unique_id(self.hass, user_input)
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                self._config.update(user_input)
                return await self.async_step_comfort()

        schema = await build_inputs_schema(self.hass, user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_comfort(self, user_input: ConfigType | None = None) -> ConfigFlowResult:
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

    async def async_step_device(self, user_input: ConfigType | None = None) -> ConfigFlowResult:
        """Adjust device settings."""
        user_input = user_input or {}
        errors: ErrorsType = {}

        if user_input:
            self._config.update(user_input)
            config = DATA_SCHEMA(self._config)
            return self.async_create_entry(title=user_input[CONF_NAME], data=config)

        schema = build_device_schema(user_input)

        return self.async_show_form(step_id="device", data_schema=schema, errors=errors)

    async def async_step_reconfigure(
        self, user_input: ConfigType | None = None
    ) -> ConfigFlowResult:
        """Change the weather provider and sensors of an existing entry."""
        entry = self._get_reconfigure_entry()
        errors: ErrorsType = {}

        if user_input:
            errors = _validate_inputs(self.hass, user_input)
            if not errors:
                # The entry keeps its unique ID (entity and device IDs are derived
                # from it), but another entry may not already use these inputs.
                unique_id = _create_unique_id(self.hass, user_input)
                if any(
                    other.unique_id == unique_id
                    for other in self._async_current_entries(include_ignore=False)
                    if other.entry_id != entry.entry_id
                ):
                    return self.async_abort(reason="already_configured")
                return self.async_update_reload_and_abort(entry, data_updates=user_input)

        schema = await build_inputs_schema(self.hass, user_input or entry.data)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return ComfortAdvisorOptionsFlow()


class ComfortAdvisorOptionsFlow(OptionsFlow):
    """Handle options."""

    def __init__(self) -> None:
        """Initialize options flow."""
        self._config: dict[str, Any] = {}

    @property
    def _original(self) -> Mapping[str, Any]:
        return self.config_entry.data | self.config_entry.options

    async def async_step_init(self, user_input: ConfigType | None = None) -> ConfigFlowResult:
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

    async def async_step_device(self, user_input: ConfigType | None = None) -> ConfigFlowResult:
        """Adjust device settings."""
        user_input = user_input or {}
        errors: ErrorsType = {}

        if user_input:
            self._config.update(user_input)
            return self.async_create_entry(title=user_input[CONF_NAME], data=self._config)

        schema = build_device_schema(self._original)

        return self.async_show_form(step_id="device", data_schema=schema, errors=errors)
