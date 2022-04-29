"""Tests for config flows."""
from __future__ import annotations

from hashlib import md5
import logging
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import (
    CONF_LATITUDE,
    CONF_LOCATION,
    CONF_LONGITUDE,
    TEMP_FAHRENHEIT,
    Platform,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import entity_registry
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import selector
from homeassistant.helpers.typing import ConfigType
from homeassistant.requirements import RequirementsNotFound
from homeassistant.util.temperature import convert as convert_temp
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
    SENSOR_TYPES,
    WEATHER_PROVIDER_TYPES,
    ConfigValue,
)
from .helpers import create_issue_tracker_url, load_module
from .weather import WEATHER_PROVIDERS, WeatherProviderError

_LOGGER = logging.getLogger(__name__)


def get_sensors_by_device_class(
    hass: HomeAssistant,
    device_class: SensorDeviceClass,
) -> list[str]:
    """Get sensors of required class from entity registry."""

    def filter_for_device_class_sensor(state: State) -> bool:
        """Filter states by Platform.SENSOR and required device class."""
        state_device_class = state.attributes.get(
            "device_class", state.attributes.get("original_device_class")
        )
        return state.domain == Platform.SENSOR and state_device_class == device_class  # type: ignore

    def filter_our_entity_ids(entity_id: str) -> bool:
        """Filter out device_ids containing our SensorType."""
        return all(not entity_id.endswith(sensor_type) for sensor_type in SENSOR_TYPES)

    result = [
        state.entity_id
        for state in filter(
            filter_for_device_class_sensor,
            hass.states.async_all(),
        )
    ]

    result.sort()
    _LOGGER.debug("Results for %s based on device class: %s", device_class, result)

    result = list(filter(filter_our_entity_ids, result))

    _LOGGER.debug("Results after cleaning own entities: %s", result)
    return result


def _build_user_schema() -> vol.Schema:
    return vol.Schema(
        {vol.Required(str(ConfigValue.PROVIDER_TYPE)): vol.All(str, vol.In(WEATHER_PROVIDER_TYPES))}
    )


async def _build_weather_schema(
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


async def _async_test_weather_provider(
    hass: HomeAssistant,
    provider_type: str,
    user_input: ConfigType,
) -> dict[str, str]:
    provider_factory = WEATHER_PROVIDERS.get(provider_type)
    provider = provider_factory(hass, **user_input)
    try:
        await provider.realtime()
        return {}
    except WeatherProviderError as exc:
        return {"base": exc.error_key}


def _build_inputs_schema(hass: HomeAssistant, user_input: ConfigType) -> vol.Schema | None:
    temp_sensors = get_sensors_by_device_class(hass, SensorDeviceClass.TEMPERATURE)
    humidity_sensors = get_sensors_by_device_class(hass, SensorDeviceClass.HUMIDITY)
    if not temp_sensors or not humidity_sensors:
        return None

    return vol.Schema(
        {
            vol.Required(
                str(ConfigValue.IN_TEMP_SENSOR),
                default=user_input.get(ConfigValue.IN_TEMP_SENSOR),
            ): vol.In(temp_sensors),
            vol.Required(
                str(ConfigValue.IN_HUMIDITY_SENSOR),
                default=user_input.get(ConfigValue.IN_HUMIDITY_SENSOR),
            ): vol.In(humidity_sensors),
            vol.Required(
                str(ConfigValue.OUT_TEMP_SENSOR),
                default=user_input.get(ConfigValue.OUT_TEMP_SENSOR),
            ): vol.In(temp_sensors),
            vol.Required(
                str(ConfigValue.OUT_HUMIDITY_SENSOR),
                default=user_input.get(ConfigValue.OUT_HUMIDITY_SENSOR),
            ): vol.In(humidity_sensors),
        }
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


def _build_settings_schema(user_input: ConfigType) -> vol.Schema | None:
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
        ent_reg.async_get(user_input[key]).unique_id
        for key in (
            ConfigValue.IN_TEMP_SENSOR,
            ConfigValue.IN_HUMIDITY_SENSOR,
            ConfigValue.OUT_TEMP_SENSOR,
            ConfigValue.OUT_HUMIDITY_SENSOR,
        )
    ]
    return md5(str(values).encode("utf8")).hexdigest()


class ComfortAdvisorConfigFlow(ConfigFlow, domain=DOMAIN):  # type: ignore
    """Configuration flow for setting up new comfort_advisor entry."""

    def __init__(self) -> None:
        """TODO."""

        self._config: dict[ConfigType, Any] = {}
        self._user_schema: vol.Schema | None = None
        self._provider_name: str | None = None
        self._weather_schema: vol.Schema | None = None
        self._weather_description: str | None = None
        self._inputs_schema: vol.Schema | None = None
        self._comfort_schema: vol.Schema | None = None
        self._settings_schema: vol.Schema | None = None

    # @staticmethod
    # @callback
    # def async_get_options_flow(config_entry: ConfigEntry):
    #    """Get the options flow for this handler."""
    #    return ComfortAdvisorOptionsFlow(config_entry)

    async def async_step_user(self, user_input: ConfigType | None = None) -> FlowResult:
        """Handle a flow initialized by the user. Choose a weather provider."""
        user_input = user_input or {}

        if ConfigValue.PROVIDER_TYPE in user_input:
            self._provider_name = user_input[ConfigValue.PROVIDER_TYPE]
            return await self.async_step_weather()

        if len(WEATHER_PROVIDER_TYPES) == 1:
            self._provider_name = list(WEATHER_PROVIDER_TYPES.keys())[0]
            return await self.async_step_weather()

        self._user_schema = self._user_schema or _build_user_schema()

        return self.async_show_form(step_id="user", data_schema=self._user_schema)

    async def async_step_weather(self, user_input: ConfigType | None = None) -> FlowResult:
        """Enter weather provider configuration."""
        user_input = user_input or {}
        errors: dict[str, str] = {}

        assert self._provider_name is not None

        if not self._weather_schema:
            try:
                module = await load_module(self.hass, self._provider_name)
            except (ImportError, RequirementsNotFound) as exc:
                issue_url = await create_issue_tracker_url(
                    self.hass,
                    exc,
                    title=f"Error loading '{self._provider_name}' weather provider",
                )

                return self.async_abort(
                    reason="load_provider",
                    description_placeholders={
                        "provider": self._provider_name,
                        "message": exc.msg,
                        "issue_tracker": issue_url,
                    },
                )

            self._weather_description = module.DESCRIPTION

            self._weather_schema = await _build_weather_schema(self.hass, module.SCHEMA, user_input)

        if user_input or not self._weather_schema.schema:
            user_input[ConfigValue.PROVIDER_TYPE] = self._provider_name
            errors = await _async_test_weather_provider(self.hass, self._provider_name, user_input)
            if not errors:
                provider_config = {ConfigValue.WEATHER_PROVIDER: user_input}
                self._config.update(provider_config)
                return await self.async_step_inputs(user_input={})

        return self.async_show_form(
            step_id="weather",
            data_schema=self._weather_schema,
            description_placeholders={"weather_desc": self._weather_description},
            errors=errors,
        )

    async def async_step_inputs(self, user_input: ConfigType | None = None) -> FlowResult:
        """Select temperature and humidity sensors."""
        user_input = user_input or {}
        errors: dict[str, str] = {}

        self._inputs_schema = self._inputs_schema or _build_inputs_schema(self.hass, user_input)

        if ConfigValue.IN_TEMP_SENSOR in user_input:
            self._config.update(user_input)
            return await self.async_step_comfort(user_input={})

        return self.async_show_form(
            step_id="inputs", data_schema=self._inputs_schema, errors=errors
        )

    async def async_step_comfort(self, user_input: ConfigType | None = None) -> FlowResult:
        """Adjust comfort values."""
        user_input = user_input or {}
        errors: dict[str, str] = {}

        self._comfort_schema = self._comfort_schema or _build_comfort_schema(self.hass, user_input)

        if ConfigValue.SIMMER_INDEX_MIN in user_input:
            self._config.update(user_input)
            return await self.async_step_settings(user_input={})

        temp_unit = self.hass.config.units.temperature_unit

        description_placeholders = {
            f"{x}F": round(convert_temp(x, TEMP_FAHRENHEIT, temp_unit), 1) for x in (70, 77, 83, 91)
        }

        return self.async_show_form(
            step_id="comfort",
            data_schema=self._comfort_schema,
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_settings(self, user_input: ConfigType | None = None) -> FlowResult:
        """TODO."""
        user_input = user_input or {}
        errors: dict[str, str] = {}

        self._settings_schema = self._settings_schema or _build_settings_schema(user_input)

        if ConfigValue.NAME in user_input:
            self._config.update(user_input)

            unique_id = _create_unique_id(self.hass, self._config)
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=user_input[ConfigValue.NAME],
                data=self._config,
            )

        return self.async_show_form(
            step_id="settings", data_schema=self._settings_schema, errors=errors
        )


# TODO: support options...
class ComfortAdvisorOptionsFlow(OptionsFlow):
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
