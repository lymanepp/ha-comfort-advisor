"""Sensor platform for comfort_advisor."""
from __future__ import annotations

from dataclasses import dataclass
import logging
import math
from xml.dom.minidom import Entity

from homeassistant import util
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_TEMPERATURE,
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_NAME,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    TEMP_FAHRENHEIT,
)
from homeassistant.core import Event, HomeAssistant, State
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.loader import async_get_custom_components

from .const import (
    CONF_INDOOR_HUMIDITY_SENSOR,
    CONF_INDOOR_TEMPERATURE_SENSOR,
    CONF_OUTDOOR_HUMIDITY_SENSOR,
    CONF_OUTDOOR_TEMPERATURE_SENSOR,
    CONF_POLL,
    CONF_POLL_INTERVAL,
    DEFAULT_NAME,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)
from .weather_provider import WeatherData

_LOGGER = logging.getLogger(__name__)


class RealtimeDataUpdateCoordinator(DataUpdateCoordinator[WeatherData]):
    """TODO."""


class ForecastDataUpdateCoordinator(DataUpdateCoordinator[list[WeatherData]]):
    """TODO."""


@dataclass
class DeviceState:
    """Comfort Advisor device state representation."""

    indoor_temp: float | None = None
    indoor_humidity: float | None = None
    outdoor_temp: float | None = None
    outdoor_humidity: float | None = None
    current: WeatherData | None = None
    forecast: WeatherData | None = None


class ComfortAdvisorDevice:
    """Representation of a Comfort Advisor Device."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        realtime_service=RealtimeDataUpdateCoordinator,
        forecast_service=ForecastDataUpdateCoordinator,
    ):
        """Initialize the device."""
        # device = hass.data[DOMAIN][entry.unique_id]
        config = entry.data | entry.options or {}

        self.hass = hass
        self._unique_id = entry.unique_id
        self._device_info = DeviceInfo(
            identifiers={(DOMAIN, self.unique_id)},
            name=config[CONF_NAME],
            manufacturer=DEFAULT_NAME,
            model="Virtual Device",
        )
        self._realtime_service = realtime_service
        self._forecast_service = forecast_service
        self._indoor_temp_entity = config[CONF_INDOOR_TEMPERATURE_SENSOR]
        self._indoor_humidity_entity = config[CONF_INDOOR_HUMIDITY_SENSOR]
        self._outdoor_temp_entity = config[CONF_OUTDOOR_TEMPERATURE_SENSOR]
        self._outdoor_humidity_entity = config[CONF_OUTDOOR_HUMIDITY_SENSOR]
        self._should_poll = config.get(CONF_POLL, False)

        self._state = DeviceState()

        self.extra_state_attributes = {}
        self.sensors: list[Entity] = []

        entry.async_on_unload(
            self._realtime_service.async_add_listener(self._realtime_updated)
        )
        entry.async_on_unload(
            self._forecast_service.async_add_listener(self._forecast_updated)
        )

        async_track_state_change_event(
            self.hass, self._indoor_temp_entity, self._indoor_temp_listener
        )
        async_track_state_change_event(
            self.hass, self._indoor_humidity_entity, self._indoor_humidity_listener
        )
        async_track_state_change_event(
            self.hass, self._outdoor_temp_entity, self._outdoor_temp_listener
        )
        async_track_state_change_event(
            self.hass, self._outdoor_humidity_entity, self._outdoor_humidity_listener
        )

        hass.async_create_task(
            self._update_indoor_temp(hass.states.get(self._indoor_temp_entity))
        )
        hass.async_create_task(
            self._update_indoor_humidity(hass.states.get(self._indoor_humidity_entity))
        )
        hass.async_create_task(
            self._update_outdoor_temp(hass.states.get(self._outdoor_temp_entity))
        )
        hass.async_create_task(
            self._update_outdoor_humidity(
                hass.states.get(self._outdoor_humidity_entity)
            )
        )

        hass.async_create_task(self._set_version())

        if self._should_poll:
            # TODO: this blows up if enabled
            async_track_time_interval(
                self.hass,
                self.async_update_sensors,
                config.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
            )

    def _realtime_updated(self):
        self._state.current = self._realtime_service.data

    def _forecast_updated(self):
        self._state.forecast = self._forecast_service.data

    async def _set_version(self):
        custom_components = await async_get_custom_components(self.hass)
        self._device_info["sw_version"] = custom_components[DOMAIN].version.string

    async def _indoor_temp_listener(self, event: Event) -> None:
        if (new_state := self._get_new_state(event)) is not None:
            await self._update_indoor_temp(new_state)

    async def _update_indoor_temp(self, state: State):
        if state:
            self._state.indoor_temp = self._get_temp(state)
            await self.async_update()

    async def _indoor_humidity_listener(self, event: Event) -> None:
        if (new_state := self._get_new_state(event)) is not None:
            await self._update_indoor_humidity(new_state)

    async def _update_indoor_humidity(self, state: State):
        if state:
            self._state.indoor_humidity = float(state.state)
            await self.async_update()

    async def _outdoor_temp_listener(self, event: Event) -> None:
        if (new_state := self._get_new_state(event)) is not None:
            await self._update_outdoor_temp(new_state)

    async def _update_outdoor_temp(self, state: State):
        if state:
            self._state.outdoor_temp = self._get_temp(state)
            await self.async_update()

    async def _outdoor_humidity_listener(self, event: Event) -> None:
        if (new_state := self._get_new_state(event)) is not None:
            await self._update_outdoor_humidity(new_state)

    async def _update_outdoor_humidity(self, state: State):
        if state:
            self._state.outdoor_humidity = float(state.state)
            await self.async_update()

    def _get_temp(self, state: State) -> float:
        temperature = float(state.state)
        if unit := state.attributes.get(ATTR_UNIT_OF_MEASUREMENT):
            temperature = self.hass.config.units.temperature(temperature, unit)
        return temperature

    @staticmethod
    def _get_new_state(event: Event) -> State | None:
        state: State = event.data.get("new_state")
        if state.state not in (None, STATE_UNKNOWN, STATE_UNAVAILABLE):
            try:
                if not math.isnan(float(state.state)):
                    return state
            except ValueError:
                pass
        return None

    async def async_update(self) -> None:
        """Update the state."""
        if not self._should_poll:
            await self.async_update_sensors(force_refresh=True)

    async def async_update_sensors(self, force_refresh: bool = False) -> None:
        """Update the state of the sensors."""
        if (
            self._state.indoor_temp is not None
            and self._state.indoor_humidity is not None
            and self._state.indoor_temp is not None
            and self._state.indoor_humidity is not None
            and self._state.current is not None
            and self._state.forecast is not None
        ):
            for sensor in self.sensors:
                sensor.async_schedule_update_ha_state(force_refresh)

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return self._unique_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return self._device_info

    @property
    def name(self) -> str:
        """Return the name."""
        return self._device_info["name"]
