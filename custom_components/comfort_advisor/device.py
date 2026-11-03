"""Device for comfort_advisor."""

from collections.abc import Mapping
import contextlib
from datetime import datetime, timedelta
import math
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_DEVICE_CLASS, ATTR_UNIT_OF_MEASUREMENT, CONF_NAME
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.util.json import JsonValueType
from homeassistant.util.unit_conversion import TemperatureConverter as TC

from .comfort import ComfortCalculator, Input
from .const import (
    _LOGGER,
    CONF_INDOOR_HUMIDITY,
    CONF_INDOOR_TEMPERATURE,
    CONF_WEATHER,
    DEFAULT_MANUFACTURER,
    DEFAULT_NAME,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)
from .helpers import async_subscribe_forecast, get_entity_area

type ComfortAdvisorConfigEntry = ConfigEntry[ComfortAdvisorDevice]


class ComfortAdvisorDevice:
    """Representation of a Comfort Advisor Device."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        sw_version: str | None = None,
    ) -> None:
        """Initialize the device."""
        self._config = config_entry.data | config_entry.options
        self.hass = hass
        self.unique_id = config_entry.unique_id
        self._comfort = ComfortCalculator(hass.config.units, self._config)

        suggested_area = get_entity_area(
            hass, self._config[CONF_INDOOR_TEMPERATURE]
        ) or get_entity_area(hass, self._config[CONF_INDOOR_HUMIDITY])

        assert self.unique_id

        self.device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, self.unique_id)},
            manufacturer=DEFAULT_MANUFACTURER,
            model=DEFAULT_NAME,
            name=self._config[CONF_NAME],
            suggested_area=suggested_area,
            sw_version=sw_version,
        )

        self._temp_unit = self.hass.config.units.temperature_unit
        self._entities: list[Entity] = []
        self._first_time = True

        self._entity_id_to_input: dict[str, Input] = {
            self._config[input]: input
            for input in [
                Input.INDOOR_TEMPERATURE,
                Input.INDOOR_HUMIDITY,
                Input.OUTDOOR_TEMPERATURE,
                Input.OUTDOOR_HUMIDITY,
            ]
        }

    async def async_setup_entry(self, config_entry: ConfigEntry) -> bool:
        """Set up device."""
        assert config_entry.unique_id

        @callback
        def forecast_listener(forecast: list[JsonValueType] | None) -> None:
            self._comfort.update_input(Input.FORECAST, forecast or None)
            self._update_if_first_time()

        weather_entity_id = self._config[CONF_WEATHER]
        unsubscribe = await async_subscribe_forecast(
            self.hass, weather_entity_id, "hourly", forecast_listener
        )
        if unsubscribe is None:
            _LOGGER.warning("Weather entity not found: %s", weather_entity_id)
            return False

        config_entry.async_on_unload(unsubscribe)

        config_entry.async_on_unload(
            async_track_state_change_event(
                self.hass, self._entity_id_to_input.keys(), self._input_event_handler
            )
        )

        for entity_id in self._entity_id_to_input:
            self._update_input_from_state(entity_id, self.hass.states.get(entity_id))

        config_entry.async_on_unload(
            async_track_time_interval(
                self.hass,
                self._async_update_scheduled,
                timedelta(seconds=DEFAULT_POLL_INTERVAL),
            )
        )
        return True

    @property
    def available(self) -> bool:
        """Whether the calculated values are available."""
        return self._comfort.available

    def get_calculated(self, name: str, default: Any = None) -> Any:
        """Retrieve calculated comfort state."""
        return self._comfort.get_calculated(name, default)

    @property
    def extra_attributes(self) -> Mapping[str, Any]:
        """Extra attributes for the "can open windows" sensor."""
        return self._comfort.extra_attributes

    def add_entity(self, entity: Entity) -> CALLBACK_TYPE:
        """Add entity to receive callback when the calculated state is updated."""
        self._entities.append(entity)
        return lambda: self._entities.remove(entity)

    # Internal methods

    async def _input_event_handler(self, event: Event[EventStateChangedData]) -> None:
        self._update_input_from_state(event.data["entity_id"], event.data["new_state"])

    def _update_input_from_state(self, entity_id: str, state: State | None) -> None:
        """Feed a sensor state to the calculator; unavailable states clear the input."""
        value = self._get_state_value(state) if state else None

        if value is not None and state is not None:
            device_class: str | None = state.attributes.get(ATTR_DEVICE_CLASS)
            if device_class == SensorDeviceClass.TEMPERATURE:
                unit: str | None = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
                if unit and unit != self._temp_unit:
                    value = TC.convert(value, unit, self._temp_unit)

        self._comfort.update_input(self._entity_id_to_input[entity_id], value)
        self._update_if_first_time()

    @staticmethod
    def _get_state_value(state: State) -> float | None:
        with contextlib.suppress(ValueError):
            value = float(state.state)
            if not math.isnan(value):
                return value
        return None

    # `async_track_time_interval` adds a `now` arg that must be stripped
    async def _async_update_scheduled(self, _: datetime) -> None:
        await self._async_update()

    def _update_if_first_time(self) -> None:
        if self._first_time:
            self.hass.async_create_task(self._async_update())

    async def _async_update(self, force_refresh: bool = True) -> None:
        if self._comfort.refresh_state():
            self._first_time = False
            for entity in self._entities:
                entity.async_schedule_update_ha_state(force_refresh)
