"""Sensor platform for comfort_advisor."""
from __future__ import annotations

from dataclasses import dataclass
import logging
import math
from xml.dom.minidom import Entity

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
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
from homeassistant.util.temperature import convert as convert_temp

from .const import (
    CONF_IN_HUMIDITY_ENTITY,
    CONF_IN_TEMP_ENTITY,
    CONF_OUT_HUMIDITY_ENTITY,
    CONF_OUT_TEMP_ENTITY,
    CONF_POLL,
    CONF_POLL_INTERVAL,
    DEFAULT_NAME,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)
from .formulas import dew_point, simmer_index
from .weather_provider import WeatherData

_LOGGER = logging.getLogger(__name__)


class RealtimeDataUpdateCoordinator(DataUpdateCoordinator[WeatherData]):
    """TODO."""


class ForecastDataUpdateCoordinator(DataUpdateCoordinator[list[WeatherData]]):
    """TODO."""


@dataclass
class DeviceState:
    """Comfort Advisor device state representation."""

    in_temp: float | None = None
    in_humidity: float | None = None
    out_temp: float | None = None
    out_humidity: float | None = None
    current: WeatherData | None = None
    forecast: list[WeatherData] | None = None


class ComfortAdvisorDevice:
    """Representation of a Comfort Advisor Device."""

    open_windows: bool
    open_windows_reason: str
    # time_until_change: timedelta

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        realtime_service=RealtimeDataUpdateCoordinator,
        forecast_service=ForecastDataUpdateCoordinator,
    ):
        """Initialize the device."""
        config = config_entry.data | config_entry.options or {}

        self.hass = hass
        self._unique_id = config_entry.unique_id
        self._device_info = DeviceInfo(
            identifiers={(DOMAIN, self.unique_id)},
            name=config[CONF_NAME],
            manufacturer=DEFAULT_NAME,
            model="Virtual Device",
        )
        self._realtime_service = realtime_service
        self._forecast_service = forecast_service
        self._in_temp_entity = config[CONF_IN_TEMP_ENTITY]
        self._in_humidity_entity = config[CONF_IN_HUMIDITY_ENTITY]
        self._out_temp_entity = config[CONF_OUT_TEMP_ENTITY]
        self._out_humidity_entity = config[CONF_OUT_HUMIDITY_ENTITY]
        self._should_poll = config.get(CONF_POLL, False)

        self.temp_unit = self.hass.config.units.temperature_unit

        # these need to come from configuration
        self.dewp_comfort_max = convert_temp(60, TEMP_FAHRENHEIT, self.temp_unit)
        self.ssi_comfort_min = convert_temp(77, TEMP_FAHRENHEIT, self.temp_unit)
        self.ssi_comfort_max = convert_temp(83, TEMP_FAHRENHEIT, self.temp_unit)
        self.rh_max = 97.0

        self._state = DeviceState()

        self.extra_state_attributes = {}
        self.sensors: list[Entity] = []

        config_entry.async_on_unload(
            self._realtime_service.async_add_listener(self._realtime_updated)
        )
        config_entry.async_on_unload(
            self._forecast_service.async_add_listener(self._forecast_updated)
        )

        async_track_state_change_event(
            self.hass, self._in_temp_entity, self._in_temp_listener
        )
        async_track_state_change_event(
            self.hass, self._in_humidity_entity, self._in_humidity_listener
        )
        async_track_state_change_event(
            self.hass, self._out_temp_entity, self._out_temp_listener
        )
        async_track_state_change_event(
            self.hass, self._out_humidity_entity, self._out_humidity_listener
        )

        hass.async_create_task(
            self._update_in_temp(hass.states.get(self._in_temp_entity))
        )
        hass.async_create_task(
            self._update_in_humidity(hass.states.get(self._in_humidity_entity))
        )
        hass.async_create_task(
            self._update_out_temp(hass.states.get(self._out_temp_entity))
        )
        hass.async_create_task(
            self._update_out_humidity(hass.states.get(self._out_humidity_entity))
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

    async def _in_temp_listener(self, event: Event) -> None:
        if (new_state := self._get_new_state(event)) is not None:
            await self._update_in_temp(new_state)

    async def _update_in_temp(self, state: State):
        if state:
            self._state.in_temp = self._get_temp(state)
            await self.async_update()

    async def _in_humidity_listener(self, event: Event) -> None:
        if (new_state := self._get_new_state(event)) is not None:
            await self._update_in_humidity(new_state)

    async def _update_in_humidity(self, state: State):
        if state:
            self._state.in_humidity = float(state.state)
            await self.async_update()

    async def _out_temp_listener(self, event: Event) -> None:
        if (new_state := self._get_new_state(event)) is not None:
            await self._update_out_temp(new_state)

    async def _update_out_temp(self, state: State):
        if state:
            self._state.out_temp = self._get_temp(state)
            await self.async_update()

    async def _out_humidity_listener(self, event: Event) -> None:
        if (new_state := self._get_new_state(event)) is not None:
            await self._update_out_humidity(new_state)

    async def _update_out_humidity(self, state: State):
        if state:
            self._state.out_humidity = float(state.state)
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
            self._state.in_temp is not None
            and self._state.in_humidity is not None
            and self._state.out_temp is not None
            and self._state.out_humidity is not None
            and self._state.current is not None
            and self._state.forecast is not None
        ):
            self.calculate_stuff()
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

    def calculate_stuff(self) -> None:
        """Update the state of the sensor."""

        def is_comfortable(dewp: float, ssi: float, rel_hum: float) -> bool:
            return (
                rel_hum <= self.rh_max
                and ssi <= self.ssi_comfort_max
                and dewp <= self.dewp_comfort_max
            )

        state = self._state

        hourly_comfort: list[bool] = []
        hourly_ssi: list[float] = []

        for data in state.forecast:
            dewp = dew_point(data["temp"], data["humidity"], self.temp_unit)
            ssi = simmer_index(data["temp"], data["humidity"], self.temp_unit)
            hourly_comfort.append(is_comfortable(dewp, ssi, data["humidity"]))
            hourly_ssi.append(ssi)

        in_dewp = dew_point(state.in_temp, state.in_humidity, self.temp_unit)
        in_ssi = simmer_index(state.in_temp, state.in_humidity, self.temp_unit)
        out_dewp = dew_point(state.out_temp, state.out_humidity, self.temp_unit)
        out_ssi = simmer_index(state.out_temp, state.out_humidity, self.temp_unit)

        self.open_windows, self.open_windows_reason = (
            (False, "in_more_comfortable")
            if out_ssi > in_ssi or out_dewp > in_dewp
            else (False, "out_ssi_too_high")
            if out_ssi > self.ssi_comfort_max
            else (False, "out_dewp_too_high")
            if out_dewp > self.dewp_comfort_max
            else (False, "out_rh_too_high")
            if state.out_humidity > self.rh_max
            else (False, "out_will_be_cool")
            if (
                in_ssi <= self.ssi_comfort_max
                and max(hourly_ssi) <= self.ssi_comfort_min
            )
            else (True, "in_more_comfortable")
        )

        # TODO: calculate time of next change
        # from datetime import timedelta
        # from itertools import takewhile
        # self.time_until_change = len(
        #    list(takewhile(lambda x: x == self.open_windows, hourly_comfort))
        # )
