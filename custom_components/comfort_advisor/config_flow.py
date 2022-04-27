"""Tests for config flows."""
from __future__ import annotations

from hashlib import sha1
import logging
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import (
    CONF_LATITUDE,
    CONF_LOCATION,
    CONF_LONGITUDE,
    CONF_NAME,
    CONF_TYPE,
    Platform,
)
from homeassistant.core import HomeAssistant, State  # , callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import entity_registry
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from .const import (
    CONF_ENABLED_SENSORS,
    CONF_IN_HUMIDITY_ENTITY,
    CONF_IN_TEMP_ENTITY,
    CONF_OUT_HUMIDITY_ENTITY,
    CONF_OUT_TEMP_ENTITY,
    CONF_POLL,
    CONF_POLL_INTERVAL,
    CONF_WEATHER_PROVIDER,
    DEFAULT_NAME,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    POLL_DEFAULT,
    WEATHER_PROVIDER_NAMES,
)
from .helpers import load_module
from .sensor import SensorType
from .weather_provider import WEATHER_PROVIDERS, WeatherProviderError

_LOGGER = logging.getLogger(__name__)


def get_sensors_by_device_class(
    hass: HomeAssistant,
    device_class: SensorDeviceClass,
) -> list[str]:
    """Get sensors of required class from entity registry."""

    def filter_by_device_class(
        _state: State, _list: list[SensorDeviceClass], should_be_in: bool = True
    ) -> bool:
        """Filter state objects by device class."""
        collected_device_class = _state.attributes.get(
            "device_class", _state.attributes.get("original_device_class")
        )
        # XNOR
        return not (collected_device_class in _list) ^ should_be_in

    def filter_for_device_class_sensor(state: State) -> bool:
        """Filter states by Platform.SENSOR and required device class."""
        return state.domain == Platform.SENSOR and filter_by_device_class(
            state, [device_class], should_be_in=True
        )

    def filter_comfort_advisor_ids(entity_id: str) -> bool:
        """Filter out device_ids containing our SensorType."""
        return all(not entity_id.endswith(sensor_type) for sensor_type in SensorType)

    result = [
        state.entity_id
        for state in filter(
            filter_for_device_class_sensor,
            hass.states.async_all(),
        )
    ]

    result.sort()
    _LOGGER.debug("Results for %s based on device class: %s", device_class, result)

    result = list(filter(filter_comfort_advisor_ids, result))

    _LOGGER.debug("Results after cleaning own entities: %s", result)
    return result


def build_schema(
    hass: HomeAssistant,
    config_entry: ConfigEntry | None,
    step: str = "user",
) -> vol.Schema:
    """Build configuration schema.

    :param config_entry: config entry for getting current parameters on None
    :param hass: Home Assistant instance
    :param show_advanced: bool: should we show advanced options?
    :param step: for which step we should build schema
    :return: Configuration schema with default parameters
    """
    humidity_sensors = get_sensors_by_device_class(hass, SensorDeviceClass.HUMIDITY)
    temperature_sensors = get_sensors_by_device_class(
        hass, SensorDeviceClass.TEMPERATURE
    )

    if not temperature_sensors or not humidity_sensors:
        return None

    config = config_entry.data | config_entry.options or {} if config_entry else {}

    default_location = {
        CONF_LATITUDE: hass.config.latitude,
        CONF_LONGITUDE: hass.config.longitude,
    }
    default_location = config.get(CONF_LOCATION, default_location)

    schema = {
        vol.Required(CONF_NAME, default=config.get(CONF_NAME, DEFAULT_NAME)): str,
        vol.Required(
            CONF_IN_TEMP_ENTITY,
            default=config.get(CONF_IN_TEMP_ENTITY, temperature_sensors[0]),
        ): vol.In(temperature_sensors),
        vol.Required(
            CONF_IN_HUMIDITY_ENTITY,
            default=config.get(CONF_IN_HUMIDITY_ENTITY, humidity_sensors[0]),
        ): vol.In(humidity_sensors),
        vol.Required(
            CONF_OUT_TEMP_ENTITY,
            default=config.get(CONF_OUT_TEMP_ENTITY, temperature_sensors[0]),
        ): vol.In(temperature_sensors),
        vol.Required(
            CONF_OUT_HUMIDITY_ENTITY,
            default=config.get(CONF_OUT_HUMIDITY_ENTITY, humidity_sensors[0]),
        ): vol.In(humidity_sensors),
        vol.Optional(CONF_POLL, default=config.get(CONF_POLL, POLL_DEFAULT)): bool,
        vol.Optional(
            CONF_POLL_INTERVAL,
            default=config.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
        ): vol.All(vol.Coerce(int), vol.Range(min=1)),
    }

    if step == "user":
        schema |= {
            vol.Optional(
                CONF_ENABLED_SENSORS,
                default=list(SensorType),
            ): cv.multi_select(
                {sensor_type: str(sensor_type).title() for sensor_type in SensorType}
            ),
        }

    return vol.Schema(schema)


def check_input(hass: HomeAssistant, user_input: ConfigType) -> dict[str, str]:
    """Check that we may use suggested configuration.

    :param hass: hass instance
    :param user_input: user input
    :returns: dict with error.
    """

    errors = {}

    it_sensor = hass.states.get(user_input[CONF_IN_TEMP_ENTITY])
    ih_sensor = hass.states.get(user_input[CONF_IN_HUMIDITY_ENTITY])
    ot_sensor = hass.states.get(user_input[CONF_OUT_TEMP_ENTITY])
    oh_sensor = hass.states.get(user_input[CONF_OUT_HUMIDITY_ENTITY])

    if it_sensor is None:
        errors["base"] = "in_temp_not_found"

    if ih_sensor is None:
        errors["base"] = "in_humidity_not_found"

    if ot_sensor is None:
        errors["base"] = "out_temp_not_found"

    if oh_sensor is None:
        errors["base"] = "out_humidity_not_found"

    return errors


class ComfortAdvisorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configuration flow for setting up new comfort_advisor entry."""

    def __init__(self) -> None:
        """TODO."""
        self._provider_type: str | None = None
        self._provider_options: dict[str, Any] | None = None

    # @staticmethod
    # @callback
    # def async_get_options_flow(config_entry: ConfigEntry):
    #    """Get the options flow for this handler."""
    #    return ComfortAdvisorOptionsFlow(config_entry)

    async def async_step_user(self, user_input: ConfigType | None = None) -> FlowResult:
        """Handle a flow initialized by the user. Choose a weather provider."""
        user_input = user_input or {}
        if user_input:
            self._provider_type = user_input[CONF_WEATHER_PROVIDER]
            return await self.async_step_weather()

        if len(WEATHER_PROVIDER_NAMES) == 1:
            self._provider_type = WEATHER_PROVIDER_NAMES[0]
            return await self.async_step_weather()

        config_schema = vol.Schema(
            {vol.Required(CONF_WEATHER_PROVIDER): vol.In(WEATHER_PROVIDER_NAMES)}
        )
        return self.async_show_form(step_id="user", data_schema=config_schema)

    async def async_step_weather(
        self, user_input: ConfigType | None = None
    ) -> FlowResult:
        """Enter weather provider configuration."""
        user_input = user_input or {}
        errors = {}
        if user_input:
            await self._async_test_weather_data(user_input, errors)
            if not errors:
                self._provider_options = dict(user_input)
                return await self.async_step_sensors()

        config_schema = await self._async_create_weather_schema(user_input)
        if config_schema is None:
            self._provider_options = {}
            return await self.async_step_sensors()

        return self.async_show_form(
            step_id="weather", data_schema=config_schema, errors=errors
        )

    async def async_step_sensors(
        self, user_input: ConfigType | None = None
    ) -> FlowResult:
        """Select temperature and humidity sensors."""
        user_input = user_input or {}
        errors = {}
        if user_input:
            unique_id = self._create_unique_id(user_input)
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            weather_provider = dict(
                {CONF_TYPE: self._provider_type}, **self._provider_options
            )
            config = dict({CONF_WEATHER_PROVIDER: weather_provider}, **user_input)

            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data=config,
            )

        if (config_schema := self._create_sensors_schema(user_input)) is None:
            reason = "no_sensors"
            return self.async_abort(reason=reason)

        return self.async_show_form(
            step_id="sensors", data_schema=config_schema, errors=errors
        )

    async def _async_create_weather_schema(
        self, user_input: ConfigType
    ) -> vol.Schema | None:
        module = await load_module(self.hass, self._provider_type)
        config_schema: vol.Schema = module.CONFIG_SCHEMA
        if not config_schema.schema:
            return None

        default_location = (
            user_input[CONF_LOCATION]
            if CONF_LOCATION in user_input
            else {
                CONF_LATITUDE: self.hass.config.latitude,
                CONF_LONGITUDE: self.hass.config.longitude,
            }
        )
        # Update imported provider schema to include default location
        return vol.Schema(
            {
                (
                    vol.Required(CONF_LOCATION, default=default_location)
                    if key == CONF_LOCATION
                    else key
                ): value
                for key, value in config_schema.schema.items()
            }
        )

    async def _async_test_weather_data(
        self, user_input: ConfigType, errors: dict[str, str]
    ) -> None:
        provider_factory = WEATHER_PROVIDERS.get(self._provider_type)
        provider = provider_factory(self.hass, **user_input)
        try:
            await provider.realtime()
        except WeatherProviderError as exc:
            errors["base"] = exc.error_key

    def _create_sensors_schema(self, user_input: ConfigType) -> vol.Schema | None:
        temp_sensors = get_sensors_by_device_class(
            self.hass, SensorDeviceClass.TEMPERATURE
        )
        humidity_sensors = get_sensors_by_device_class(
            self.hass, SensorDeviceClass.HUMIDITY
        )
        if not temp_sensors or not humidity_sensors:
            return None

        return vol.Schema(
            {
                vol.Required(
                    CONF_NAME, default=user_input.get(CONF_NAME, DEFAULT_NAME)
                ): str,
                vol.Required(
                    CONF_IN_TEMP_ENTITY,
                    default=user_input.get(CONF_IN_TEMP_ENTITY),
                ): vol.In(temp_sensors),
                vol.Required(
                    CONF_IN_HUMIDITY_ENTITY,
                    default=user_input.get(CONF_IN_HUMIDITY_ENTITY),
                ): vol.In(humidity_sensors),
                vol.Required(
                    CONF_OUT_TEMP_ENTITY,
                    default=user_input.get(CONF_OUT_TEMP_ENTITY),
                ): vol.In(temp_sensors),
                vol.Required(
                    CONF_OUT_HUMIDITY_ENTITY,
                    default=user_input.get(CONF_OUT_HUMIDITY_ENTITY),
                ): vol.In(humidity_sensors),
                vol.Optional(
                    CONF_POLL, default=user_input.get(CONF_POLL, POLL_DEFAULT)
                ): bool,
                vol.Optional(
                    CONF_POLL_INTERVAL,
                    default=user_input.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=1)),
            }
        )

    def _create_unique_id(self, user_input: ConfigType) -> str:
        ent_reg = entity_registry.async_get(self.hass)
        values = [
            ent_reg.async_get(user_input[key]).unique_id
            for key in (
                CONF_IN_TEMP_ENTITY,
                CONF_IN_HUMIDITY_ENTITY,
                CONF_OUT_TEMP_ENTITY,
                CONF_OUT_HUMIDITY_ENTITY,
            )
        ]
        values.append(self._provider_type)
        values.append(self._provider_options)
        return sha1(str(values).encode("utf8")).hexdigest()


# TODO: support options...
class ComfortAdvisorOptionsFlow(OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry: ConfigEntry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input: ConfigType = None):
        """Manage the options."""

        errors = {}
        if user_input is not None:
            _LOGGER.debug("OptionsFlow: going to update configuration %s", user_input)
            if not (errors := check_input(self.hass, user_input)):
                return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=build_schema(
                hass=self.hass, config_entry=self.config_entry, step="init"
            ),
            errors=errors,
        )
