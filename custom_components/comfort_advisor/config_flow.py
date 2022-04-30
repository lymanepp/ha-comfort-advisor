"""Tests for config flows."""
from __future__ import annotations

from hashlib import md5
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_LATITUDE,
    CONF_LOCATION,
    CONF_LONGITUDE,
    PERCENTAGE,
    TEMP_FAHRENHEIT,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import entity_registry
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import selector
from homeassistant.helpers.typing import ConfigType
from homeassistant.requirements import RequirementsNotFound
from homeassistant.util.temperature import (
    VALID_UNITS as TEMPERATURE_UNITS,
    convert as convert_temp,
)
import voluptuous as vol

from .const import (
    DEFAULT_DEWPOINT_MAX,
    DEFAULT_HUMIDITY_MAX,
    DEFAULT_NAME,
    DEFAULT_POLL,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_POLLEN_MAX,
    DEFAULT_SIMMER_INDEX_MAX,
    DEFAULT_SIMMER_INDEX_MIN,
    DOMAIN,
    PROVIDER_TYPES,
    SENSOR_TYPES,
    ConfigSchema,
    ConfigValue,
)
from .helpers import create_issue_tracker_url, load_module
from .provider import PROVIDER_SCHEMA, PROVIDERS, ProviderError

temp_sensor_selector = selector(
    {"entity": {"domain": "sensor", "device_class": SensorDeviceClass.TEMPERATURE}}
)
humidity_sensor_selector = selector(
    {"entity": {"domain": "sensor", "device_class": SensorDeviceClass.HUMIDITY}}
)


def _build_weather_schema(
    hass: HomeAssistant, config_schema: vol.Schema, user_input: ConfigType
) -> vol.Schema:
    default_location = (
        user_input[CONF_LOCATION]
        if CONF_LOCATION in user_input
        else {
            CONF_LATITUDE: hass.config.latitude,
            CONF_LONGITUDE: hass.config.longitude,
        }
    )
    # Update provider's schema to have default location
    return vol.Schema(
        {
            (
                type(key)(CONF_LOCATION, default=default_location) if key == CONF_LOCATION else key
            ): value
            for key, value in config_schema.schema.items()
        }
    )


async def _async_test_weather(
    hass: HomeAssistant, provider_config: ConfigType, errors: dict[str, str]
) -> bool:
    provider_type = provider_config[ConfigValue.TYPE]
    provider_factory = PROVIDERS.get(provider_type)
    provider = provider_factory(hass, **provider_config)
    try:
        await provider.realtime()
        return True
    except ProviderError as exc:
        errors["base"] = exc.error_key
        return False


def _build_inputs_schema(user_input: ConfigType) -> vol.Schema | None:
    return vol.Schema(
        {
            vol.Required(
                str(ConfigValue.INDOOR_TEMPERATURE),
                default=user_input.get(ConfigValue.INDOOR_TEMPERATURE),
            ): temp_sensor_selector,
            vol.Required(
                str(ConfigValue.INDOOR_HUMIDITY),
                default=user_input.get(ConfigValue.INDOOR_HUMIDITY),
            ): humidity_sensor_selector,
            vol.Required(
                str(ConfigValue.OUTDOOR_TEMPERATURE),
                default=user_input.get(ConfigValue.OUTDOOR_TEMPERATURE),
            ): temp_sensor_selector,
            vol.Required(
                str(ConfigValue.OUTDOOR_HUMIDITY),
                default=user_input.get(ConfigValue.OUTDOOR_HUMIDITY),
            ): humidity_sensor_selector,
        }
    )


def _async_test_inputs(hass: HomeAssistant, user_input: ConfigType, errors: dict[str, str]) -> bool:
    def check_sensor_units(keys: list[str], valid_units: list[str]) -> bool:
        for key in keys:
            state: State = hass.states.get(user_input[key])
            unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
            if unit not in valid_units:
                errors["base"] = "sensor_units"
                return False
        return True

    return check_sensor_units(
        [ConfigValue.INDOOR_TEMPERATURE, ConfigValue.OUTDOOR_TEMPERATURE], TEMPERATURE_UNITS
    ) and check_sensor_units(
        [ConfigValue.INDOOR_HUMIDITY, ConfigValue.OUTDOOR_HUMIDITY], [PERCENTAGE]
    )


def _build_comfort_schema(hass: HomeAssistant, user_input: ConfigType) -> vol.Schema | None:

    temp_unit = hass.config.units.temperature_unit
    dewp_max = round(convert_temp(DEFAULT_DEWPOINT_MAX, TEMP_FAHRENHEIT, temp_unit), 1)
    ssi_max = round(convert_temp(DEFAULT_SIMMER_INDEX_MAX, TEMP_FAHRENHEIT, temp_unit), 1)
    ssi_min = round(convert_temp(DEFAULT_SIMMER_INDEX_MIN, TEMP_FAHRENHEIT, temp_unit), 1)

    temperature_selector = selector({"number": {"mode": "box", "unit_of_measurement": temp_unit}})
    humidity_selector = selector(
        {"number": {"mode": "slider", "unit_of_measurement": "%", "min": 90, "max": 100}}
    )
    pollen_selector = selector({"number": {"mode": "slider", "min": 0, "max": 5}})

    return vol.Schema(
        {
            vol.Required(
                str(ConfigValue.SIMMER_INDEX_MIN),
                default=user_input.get(ConfigValue.SIMMER_INDEX_MIN, ssi_min),
            ): temperature_selector,
            vol.Required(
                str(ConfigValue.SIMMER_INDEX_MAX),
                default=user_input.get(ConfigValue.SIMMER_INDEX_MAX, ssi_max),
            ): temperature_selector,
            vol.Required(
                str(ConfigValue.DEWPOINT_MAX),
                default=user_input.get(ConfigValue.DEWPOINT_MAX, dewp_max),
            ): temperature_selector,
            vol.Required(
                str(ConfigValue.HUMIDITY_MAX),
                default=user_input.get(ConfigValue.HUMIDITY_MAX, DEFAULT_HUMIDITY_MAX),
            ): vol.All(humidity_selector),
            vol.Required(
                str(ConfigValue.POLLEN_MAX),
                default=user_input.get(ConfigValue.POLLEN_MAX, DEFAULT_POLLEN_MAX),
            ): vol.All(pollen_selector),
        }
    )


def _build_device_schema(user_input: ConfigType) -> vol.Schema | None:
    sensor_type_dict = {x: x.replace("_", " ").title() for x in SENSOR_TYPES}

    return vol.Schema(
        {
            vol.Required(
                str(ConfigValue.NAME),
                default=user_input.get(ConfigValue.NAME, DEFAULT_NAME),
            ): str,
            vol.Optional(
                str(ConfigValue.ENABLED_SENSORS),
                default=SENSOR_TYPES,
            ): cv.multi_select(sensor_type_dict),
            vol.Optional(
                str(ConfigValue.POLL),
                default=user_input.get(ConfigValue.POLL, DEFAULT_POLL),
            ): bool,
            vol.Optional(
                str(ConfigValue.POLL_INTERVAL),
                default=user_input.get(ConfigValue.POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=300)),
        }
    )


def _create_unique_id(hass: HomeAssistant, user_input: ConfigType) -> str:
    ent_reg = entity_registry.async_get(hass)
    values = [
        ent_reg.async_get(user_input[ConfigSchema.INPUTS][key]).unique_id
        for key in (
            ConfigValue.INDOOR_TEMPERATURE,
            ConfigValue.INDOOR_HUMIDITY,
            ConfigValue.OUTDOOR_TEMPERATURE,
            ConfigValue.OUTDOOR_HUMIDITY,
        )
    ]
    return md5(str(values).encode("utf8")).hexdigest()


class ComfortAdvisorConfigFlow(ConfigFlow, domain=DOMAIN):  # type: ignore
    """Configuration flow for setting up new comfort_advisor entry."""

    def __init__(self) -> None:
        """TODO."""

        self._config: dict[str, Any] = {}
        self._weather_description: str | None = None
        self._settings_schema: vol.Schema | None = None

        self._schemas: dict[str, vol.Schema] = {}

    # @staticmethod
    # @callback
    # def async_get_options_flow(config_entry: ConfigEntry):
    #    """Get the options flow for this handler."""
    #    return ComfortAdvisorOptionsFlow(config_entry)

    async def async_step_user(self, user_input: ConfigType | None = None) -> FlowResult:
        """Handle a flow initialized by the user. Choose a provider."""
        user_input = user_input or {}

        if len(PROVIDER_TYPES) == 1:
            user_input = {str(ConfigValue.TYPE): list(PROVIDER_TYPES.keys())[0]}

        if user_input and PROVIDER_SCHEMA(user_input):
            self._config[ConfigSchema.PROVIDER] = user_input
            return await self.async_step_provider()

        return self.async_show_form(step_id="user", data_schema=PROVIDER_SCHEMA)

    async def async_step_provider(self, user_input: ConfigType | None = None) -> FlowResult:
        """Enter provider configuration."""
        user_input = user_input or {}
        errors: dict[str, str] = {}

        provider_type = self._config[ConfigSchema.PROVIDER][ConfigValue.TYPE]

        if (weather_schema := self._schemas.get(ConfigSchema.PROVIDER)) is None:
            try:
                module = await load_module(self.hass, provider_type)
            except (ImportError, RequirementsNotFound) as exc:
                issue_url = await create_issue_tracker_url(
                    self.hass, exc, title=f"Error loading '{provider_type}' provider"
                )
                return self.async_abort(
                    reason="load_provider",
                    description_placeholders={
                        "provider": provider_type,
                        "message": exc.msg,
                        "issue_url": issue_url,
                    },
                )
            weather_schema = self._schemas[ConfigSchema.PROVIDER] = _build_weather_schema(
                self.hass, module.SCHEMA, user_input
            )
            self._weather_description = module.DESCRIPTION

        if any(user_input) == any(weather_schema.schema):
            provider_config = dict(self._config[ConfigSchema.PROVIDER], **user_input)
            if await _async_test_weather(self.hass, provider_config, errors):
                self._config[ConfigSchema.PROVIDER] = provider_config
                return await self.async_step_inputs()

        return self.async_show_form(
            step_id="provider",
            data_schema=weather_schema,
            description_placeholders={"provider_desc": self._weather_description},
            errors=errors,
        )

    async def async_step_inputs(self, user_input: ConfigType | None = None) -> FlowResult:
        """Select temperature and humidity sensors."""
        user_input = user_input or {}
        errors: dict[str, str] = {}

        if ConfigSchema.INPUTS not in self._schemas:
            self._schemas[ConfigSchema.INPUTS] = _build_inputs_schema(user_input)

        if user_input:
            if _async_test_inputs(self.hass, user_input, errors):
                self._config[ConfigSchema.INPUTS] = user_input
                return await self.async_step_comfort(user_input={})

        return self.async_show_form(
            step_id="inputs", data_schema=self._schemas[ConfigSchema.INPUTS], errors=errors
        )

    async def async_step_comfort(self, user_input: ConfigType | None = None) -> FlowResult:
        """Adjust comfort values."""
        user_input = user_input or {}
        errors: dict[str, str] = {}

        if ConfigSchema.COMFORT not in self._schemas:
            self._schemas[ConfigSchema.COMFORT] = _build_comfort_schema(self.hass, user_input)

        if user_input:
            self._config[ConfigSchema.COMFORT] = user_input
            return await self.async_step_device(user_input={})

        temp_unit = self.hass.config.units.temperature_unit
        description_placeholders = {
            str(x): round(convert_temp(x, TEMP_FAHRENHEIT, temp_unit), 1) for x in (70, 77, 83, 91)
        }

        return self.async_show_form(
            step_id="comfort",
            data_schema=self._schemas[ConfigSchema.COMFORT],
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_device(self, user_input: ConfigType | None = None) -> FlowResult:
        """TODO."""
        user_input = user_input or {}
        errors: dict[str, str] = {}

        if ConfigSchema.DEVICE not in self._schemas:
            self._schemas[ConfigSchema.DEVICE] = _build_device_schema(user_input)

        if user_input:
            self._config[ConfigSchema.DEVICE] = user_input
            unique_id = _create_unique_id(self.hass, self._config)
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=user_input[ConfigValue.NAME],
                data=self._config,
            )

        return self.async_show_form(
            step_id="device", data_schema=self._schemas[ConfigSchema.DEVICE], errors=errors
        )


# TODO: support options...
class ComfortAdvisorOptionsFlow(OptionsFlow):  # type: ignore
    """Handle options."""

    def __init__(self, config_entry: ConfigEntry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input: ConfigType = None) -> FlowResult:
        """Manage the options."""

        # errors = {}
        # if user_input is not None:
        #    _LOGGER.debug("OptionsFlow: going to update configuration %s", user_input)
        #    if not (errors := check_input(self.hass, user_input)):
        #        return self.async_create_entry(title="", data=user_input)

        # return self.async_show_form(
        #    step_id="init",
        #    data_schema=build_schema(
        #        hass=self.hass, config_entry=self.config_entry, step="init"
        #    ),
        #    errors=errors,
        # )
