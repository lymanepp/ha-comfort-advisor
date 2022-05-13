"""Device for comfort_advisor."""
from __future__ import annotations

import contextlib
from datetime import datetime, timedelta
import logging
import math
from typing import Any, Mapping, cast

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ATTRIBUTION,
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_NAME,
)
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, State
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.loader import async_get_custom_components
from homeassistant.util.temperature import convert as convert_temp

from .comfort import ComfortCalculator, Input
from .const import (
    CONF_INDOOR_HUMIDITY,
    CONF_INDOOR_TEMPERATURE,
    DEFAULT_MANUFACTURER,
    DEFAULT_NAME,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)
from .helpers import get_entity_area
from .provider import Provider

_LOGGER = logging.getLogger(__name__)


class ComfortAdvisorDevice:
    """Representation of a Comfort Advisor Device."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        provider: Provider,
    ) -> None:
        """Initialize the device."""
        self._config = config_entry.data | config_entry.options or {}
        self.hass = hass
        self.unique_id = config_entry.unique_id
        self._comfort = ComfortCalculator(hass.config.units.temperature_unit, self._config)

        suggested_area = get_entity_area(
            hass, self._config[CONF_INDOOR_TEMPERATURE]
        ) or get_entity_area(hass, self._config[CONF_INDOOR_HUMIDITY])

        self.device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, self.unique_id)},
            manufacturer=DEFAULT_MANUFACTURER,
            model=DEFAULT_NAME,
            name=self._config[CONF_NAME],
            hw_version=provider.version,
            suggested_area=suggested_area,
        )

        self._provider = provider
        self._temp_unit = self.hass.config.units.temperature_unit
        self._entities: list[Entity] = []
        self._first_time = True

        self._extra_state_attributes: dict[str, Any] = {ATTR_ATTRIBUTION: provider.attribution}

        self._entity_id_map: dict[str, str] = {}
        for input_key in [
            Input.INDOOR_TEMPERATURE,
            Input.INDOOR_HUMIDITY,
            Input.OUTDOOR_TEMPERATURE,
            Input.OUTDOOR_HUMIDITY,
        ]:
            entity_id = self._config[input_key]
            self._entity_id_map[entity_id] = input_key

    async def async_setup_entry(self, config_entry: ConfigEntry) -> bool:
        """Set up device."""
        assert config_entry.unique_id

        config_entry.async_on_unload(
            self._provider.async_add_realtime_listener(self._realtime_updated)
        )
        config_entry.async_on_unload(
            self._provider.async_add_forecast_listener(self._forecast_updated)
        )
        config_entry.async_on_unload(
            async_track_state_change_event(
                self.hass, self._entity_id_map.keys(), self._input_event_handler
            )
        )

        for entity_id in self._entity_id_map:
            if state := self.hass.states.get(entity_id):
                self._update_input_from_state(state)

        config_entry.async_on_unload(
            async_track_time_interval(
                self.hass,
                self._async_update_scheduled,
                timedelta(seconds=DEFAULT_POLL_INTERVAL),
            )
        )

        self.hass.async_create_task(self._set_sw_version())
        return True

    @property
    def name(self) -> str:
        """Return the name."""
        return cast(str, self.device_info["name"])

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return the extra device attributes."""
        return self._extra_state_attributes

    def get_state(self, name: str, default: Any = None) -> Any:
        """Retrieve calculated comfort state."""
        return self._comfort.get_state(name, default)

    def add_entity(self, entity: Entity) -> CALLBACK_TYPE:
        """Add entity to receive callback when the calculated state is updated."""
        self._entities.append(entity)
        return lambda: self._entities.remove(entity)

    # Internal methods

    async def _set_sw_version(self) -> None:
        custom_components = await async_get_custom_components(self.hass)
        self.device_info["sw_version"] = custom_components[DOMAIN].version.string

    def _realtime_updated(self) -> None:
        self._comfort.update_input(Input.REALTIME, self._provider.realtime_service.data)
        self._update_if_first_time()

    def _forecast_updated(self) -> None:
        self._comfort.update_input(Input.FORECAST, self._provider.forecast_service.data)
        self._update_if_first_time()

    async def _input_event_handler(self, event: Event) -> None:
        state: State = event.data.get("new_state")
        _LOGGER.debug(
            "_event_handler called for %s - entity(%s) - state(%s)",
            self.device_info["name"],
            state.entity_id if state else None,
            state.state if state else None,
        )
        self._update_input_from_state(state)

    def _update_input_from_state(self, state: State) -> bool:
        _LOGGER.debug(
            "_update_with_state called for %s - entity(%s) - state(%s)",
            self.device_info["name"],
            state.entity_id if state else None,
            state.state if state else None,
        )
        if not (value := self._get_state_value(state)):
            return False

        device_class: str = state.attributes.get(ATTR_DEVICE_CLASS)
        if device_class == SensorDeviceClass.TEMPERATURE:
            unit: str = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
            if unit and unit != self._temp_unit:
                value = convert_temp(value, unit, self._temp_unit)

        input_key = self._entity_id_map[state.entity_id]
        self._comfort.update_input(input_key, value)
        self._update_if_first_time()
        return True

    @staticmethod
    def _get_state_value(state: State) -> float | None:
        with contextlib.suppress(ValueError):
            value = float(state.state)
            if not math.isnan(value):
                return value
        return None

    # `async_track_time_interval` adds a `now` arg that must be stripped
    async def _async_update_scheduled(self, now: datetime) -> None:
        await self._async_update()

    def _update_if_first_time(self) -> None:
        if self._first_time:
            self.hass.async_create_task(self._async_update())

    async def _async_update(self, force_refresh: bool = True) -> None:
        _LOGGER.debug(
            "_async_update called for %s force_refresh=%s",
            self.device_info["name"],
            str(force_refresh),
        )
        if self._comfort.refresh_state():
            self._first_time = False
            self._extra_state_attributes.update(self._comfort.extra_attributes)
            for entity in self._entities:
                entity.async_schedule_update_ha_state(force_refresh)
