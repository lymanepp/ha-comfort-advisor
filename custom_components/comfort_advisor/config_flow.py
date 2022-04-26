"""Tests for config flows."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry, OptionsFlow, ConfigFlow
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import (
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LOCATION,
    CONF_LONGITUDE,
    CONF_NAME,
    Platform,
)
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers import entity_registry
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import LocationSelector  # , LocationSelectorConfig
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from .const import (
    CONF_CUSTOM_ICONS,
    CONF_ENABLED_SENSORS,
    CONF_INDOOR_HUMIDITY_SENSOR,
    CONF_INDOOR_TEMPERATURE_SENSOR,
    CONF_OUTDOOR_HUMIDITY_SENSOR,
    CONF_OUTDOOR_TEMPERATURE_SENSOR,
    CONF_POLL,
    CONF_POLL_INTERVAL,
    CONF_WEATHER_PROVIDER,
    DEFAULT_NAME,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    POLL_DEFAULT,
)
from .sensor import SensorType
from .weather_provider import WEATHER_PROVIDER_NAMES

_LOGGER = logging.getLogger(__name__)


def get_sensors_by_device_class(
    hass: HomeAssistant,
    device_class: SensorDeviceClass,
) -> list:
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
    entry: ConfigEntry | None,
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

    config = entry.data | entry.options or {} if entry else {}

    default_location = {
        CONF_LATITUDE: hass.config.latitude,
        CONF_LONGITUDE: hass.config.longitude,
    }
    default_location = config.get(CONF_LOCATION, default_location)

    # TODO: schema needs to be dynamic based on 'CONF_WEATHER_PROVIDER'
    schema = vol.Schema(
        {
            # TODO: this needs to be dynamic based on the weather provider!!!!
            vol.Required(
                CONF_WEATHER_PROVIDER,
                default=config.get(CONF_WEATHER_PROVIDER),
            ): vol.In(WEATHER_PROVIDER_NAMES),
            vol.Required(CONF_API_KEY, default=config.get(CONF_API_KEY)): str,
            vol.Required(CONF_LOCATION, default=default_location): LocationSelector(
                config={"location": {}}  # future: LocationSelectorConfig(radius=False)
            ),
            vol.Required(CONF_NAME, default=config.get(CONF_NAME, DEFAULT_NAME)): str,
            vol.Required(
                CONF_INDOOR_TEMPERATURE_SENSOR,
                default=config.get(
                    CONF_INDOOR_TEMPERATURE_SENSOR, temperature_sensors[0]
                ),
            ): vol.In(temperature_sensors),
            vol.Required(
                CONF_INDOOR_HUMIDITY_SENSOR,
                default=config.get(CONF_INDOOR_HUMIDITY_SENSOR, humidity_sensors[0]),
            ): vol.In(humidity_sensors),
            vol.Required(
                CONF_OUTDOOR_TEMPERATURE_SENSOR,
                default=config.get(
                    CONF_OUTDOOR_TEMPERATURE_SENSOR, temperature_sensors[0]
                ),
            ): vol.In(temperature_sensors),
            vol.Required(
                CONF_OUTDOOR_HUMIDITY_SENSOR,
                default=config.get(CONF_OUTDOOR_HUMIDITY_SENSOR, humidity_sensors[0]),
            ): vol.In(humidity_sensors),
            vol.Optional(CONF_POLL, default=config.get(CONF_POLL, POLL_DEFAULT)): bool,
            vol.Optional(
                CONF_POLL_INTERVAL,
                default=config.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=1)),
            vol.Optional(
                CONF_CUSTOM_ICONS,
                default=config.get(CONF_CUSTOM_ICONS, False),
            ): bool,
        },
    )

    if step == "user":
        schema = schema.extend(
            {
                vol.Optional(
                    CONF_ENABLED_SENSORS,
                    default=list(SensorType),
                ): cv.multi_select(
                    {
                        sensor_type: str(sensor_type).title()
                        for sensor_type in SensorType
                    }
                ),
            }
        )

    return schema


def check_input(hass: HomeAssistant, user_input: ConfigType) -> dict[str, str]:
    """Check that we may use suggested configuration.

    :param hass: hass instance
    :param user_input: user input
    :returns: dict with error.
    """

    errors = {}

    it_sensor = hass.states.get(user_input[CONF_INDOOR_TEMPERATURE_SENSOR])
    ih_sensor = hass.states.get(user_input[CONF_INDOOR_HUMIDITY_SENSOR])
    ot_sensor = hass.states.get(user_input[CONF_OUTDOOR_TEMPERATURE_SENSOR])
    oh_sensor = hass.states.get(user_input[CONF_OUTDOOR_HUMIDITY_SENSOR])

    if it_sensor is None:
        errors["base"] = "indoor_temp_not_found"

    if ih_sensor is None:
        errors["base"] = "indoor_humidity_not_found"

    if ot_sensor is None:
        errors["base"] = "outdoor_temp_not_found"

    if oh_sensor is None:
        errors["base"] = "outdoor_humidity_not_found"

    # ToDo: we should not trust user and check:
    #  - that CONF_TEMPERATURE_SENSOR is temperature sensor and have state_class measurement
    #  - that CONF_HUMIDITY_SENSOR is humidity sensor and have state_class measurement
    return errors


class ComfortAdvisorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configuration flow for setting up new comfort_advisor entry."""

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return ComfortAdvisorOptionsFlow(config_entry)

    async def async_step_user(self, user_input: ConfigType = None):
        """Handle a flow initialized by the user."""
        errors = {}

        if user_input:
            if not (errors := check_input(self.hass, user_input)):
                ent_reg = entity_registry.async_get(self.hass)

                it_sensor = ent_reg.async_get(
                    user_input[CONF_INDOOR_TEMPERATURE_SENSOR]
                )
                ih_sensor = ent_reg.async_get(user_input[CONF_INDOOR_HUMIDITY_SENSOR])
                ot_sensor = ent_reg.async_get(
                    user_input[CONF_OUTDOOR_TEMPERATURE_SENSOR]
                )
                oh_sensor = ent_reg.async_get(user_input[CONF_OUTDOOR_HUMIDITY_SENSOR])

                _LOGGER.debug(
                    "Going to use %s: %s", CONF_INDOOR_TEMPERATURE_SENSOR, it_sensor
                )
                _LOGGER.debug(
                    "Going to use %s: %s", CONF_INDOOR_HUMIDITY_SENSOR, ih_sensor
                )
                _LOGGER.debug(
                    "Going to use %s: %s", CONF_OUTDOOR_TEMPERATURE_SENSOR, ot_sensor
                )
                _LOGGER.debug(
                    "Going to use %s: %s", CONF_OUTDOOR_HUMIDITY_SENSOR, oh_sensor
                )

                if it_sensor and ih_sensor and ot_sensor and oh_sensor:
                    unique_id = f"{it_sensor.unique_id}-{ih_sensor.unique_id}-{ot_sensor.unique_id}-{oh_sensor.unique_id}"
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data=user_input,
                )

        schema = build_schema(hass=self.hass, entry=None)

        if schema is None:
            reason = "no_sensors"
            return self.async_abort(reason=reason)

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )


class ComfortAdvisorOptionsFlow(OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry):
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
                hass=self.hass, entry=self.config_entry, step="init"
            ),
            errors=errors,
        )
