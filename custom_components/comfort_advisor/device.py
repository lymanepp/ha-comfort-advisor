"""Device for comfort_advisor."""
from __future__ import annotations

import math
from typing import Any, cast

from homeassistant.backports.enum import StrEnum
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ATTRIBUTION,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, State
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.loader import async_get_custom_components

from .const import (
    DEFAULT_MANUFACTURER,
    DEFAULT_NAME,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    ConfigValue,
)
from .formulas import dew_point, simmer_index
from .provider import Provider, WeatherData


class DeviceState(StrEnum):  # type: ignore
    """TODO."""

    # weather provider data
    REALTIME = "realtime"
    FORECAST = "forecast"
    # input sensors
    IN_TEMPERATURE = "in_temperature"
    IN_HUMIDITY = "in_humidity"
    OUT_TEMPERATURE = "out_temperature"
    OUT_HUMIDITY = "out_humidity"
    # calculated values
    OPEN_WINDOWS = "open_windows"
    OPEN_WINDOWS_REASON = "open_windows_reason"


class ComfortAdvisorDevice:
    """Representation of a Comfort Advisor Device."""

    open_windows: bool
    open_windows_reason: str
    # time_until_change: timedelta

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        provider: Provider,
        realtime_service: DataUpdateCoordinator[WeatherData],
        forecast_service: DataUpdateCoordinator[list[WeatherData]],
    ) -> None:
        """Initialize the device."""
        config = config_entry.data | config_entry.options or {}

        self.hass = hass
        self._unique_id = config_entry.unique_id

        self.states: dict[str, Any] = {state: None for state in DeviceState}  # type: ignore

        self._device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, self.unique_id)},
            manufacturer=DEFAULT_MANUFACTURER,
            model=DEFAULT_NAME,
            name=config[ConfigValue.NAME],
            hw_version=provider.version,
        )

        self._realtime_service = realtime_service
        self._forecast_service = forecast_service

        # comfort settings
        self._dewp_comfort_max: float = config[ConfigValue.DEWPOINT_MAX]
        self._ssi_comfort_max: float = config[ConfigValue.SIMMER_INDEX_MAX]
        self._ssi_comfort_min: float = config[ConfigValue.SIMMER_INDEX_MIN]
        self._humidity_max: int = config[ConfigValue.HUMIDITY_MAX]
        self._pollen_max: int = config[ConfigValue.POLLEN_MAX]

        # device settings
        self._should_poll: bool = config[ConfigValue.POLL]
        self._poll_interval: int = config[ConfigValue.POLL_INTERVAL]

        self._temp_unit = self.hass.config.units.temperature_unit

        self.extra_state_attributes: dict[str, Any] = {ATTR_ATTRIBUTION: provider.attribution}

        self._entities: list[Entity] = []

        config_entry.async_on_unload(
            self._realtime_service.async_add_listener(self._realtime_updated)
        )
        config_entry.async_on_unload(
            self._forecast_service.async_add_listener(self._forecast_updated)
        )

        # TODO: need common listener that updates the right state bucket
        for config_key, listener in (
            (ConfigValue.IN_TEMP_SENSOR, self._in_temp_listener),
            (ConfigValue.IN_HUMIDITY_SENSOR, self._in_humidity_listener),
            (ConfigValue.OUT_TEMP_SENSOR, self._out_temp_listener),
            (ConfigValue.OUT_HUMIDITY_SENSOR, self._out_humidity_listener),
        ):
            config_entry.async_on_unload(
                async_track_state_change_event(self.hass, config[config_key], listener)
            )

        hass.async_create_task(self._set_version())

        if self._should_poll:
            # TODO: this blows up if enabled
            async_track_time_interval(
                self.hass,
                self.async_update_entities,
                config.get(ConfigValue.POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
            )

    def add_entity(self, entity: Entity) -> CALLBACK_TYPE:
        """TODO."""
        self._entities.append(entity)
        return lambda: self._entities.remove(entity)

    def _realtime_updated(self) -> None:
        self.states[DeviceState.REALTIME] = self._realtime_service.data
        # self.states["realtime_last"] = utcnow()
        self.hass.async_create_task(self.async_update_entities())

    def _forecast_updated(self) -> None:
        self.states[DeviceState.FORECAST] = self._forecast_service.data
        # self.states["forecast_last"] = utcnow()
        self.hass.async_create_task(self.async_update_entities())

    async def _set_version(self) -> None:
        custom_components = await async_get_custom_components(self.hass)
        self._device_info["sw_version"] = custom_components[DOMAIN].version.string

    async def _in_temp_listener(self, event: Event) -> None:
        if (state := self._get_new_state(event)) is not None:
            self.states[DeviceState.IN_TEMPERATURE] = self._get_temp(state)
            await self.async_update()

    async def _in_humidity_listener(self, event: Event) -> None:
        if (state := self._get_new_state(event)) is not None:
            self.states[DeviceState.IN_HUMIDITY] = float(state.state)
            await self.async_update()

    async def _out_temp_listener(self, event: Event) -> None:
        if (state := self._get_new_state(event)) is not None:
            self.states[DeviceState.OUT_TEMPERATURE] = self._get_temp(state)
            await self.async_update()

    async def _out_humidity_listener(self, event: Event) -> None:
        if (state := self._get_new_state(event)) is not None:
            self.states[DeviceState.OUT_HUMIDITY] = float(state.state)
            await self.async_update()

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

    def _get_temp(self, state: State) -> float:
        temperature = float(state.state)
        if unit := state.attributes.get(ATTR_UNIT_OF_MEASUREMENT):
            temperature = self.hass.config.units.temperature(temperature, unit)
        return temperature

    async def async_update(self) -> None:
        """Update the state."""
        if not self._should_poll:
            await self.async_update_entities(force_refresh=True)

    async def async_update_entities(self, force_refresh: bool = False) -> None:
        """Update the state of the entities."""
        if self._calculate_state(**(self.states)):
            for entity in self._entities:
                entity.async_schedule_update_ha_state(force_refresh)

    def _all_required_states(self, required_states: list[str]) -> bool:
        return all(self.states.get(x) is not None for x in required_states)

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return self._unique_id  # type: ignore

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return self._device_info

    @property
    def name(self) -> str:
        """Return the name."""
        return cast(str, self._device_info["name"])

    def _calculate_state(  # type: ignore
        self,
        in_temperature: float | None = None,
        in_humidity: float | None = None,
        out_temperature: float | None = None,
        out_humidity: float | None = None,
        realtime: WeatherData | None = None,
        forecast: list[WeatherData] | None = None,
        **kwargs,
    ) -> bool:
        if (
            in_temperature is None
            or in_humidity is None
            or out_temperature is None
            or out_humidity is None
            or realtime is None
            or forecast is None
        ):
            return False

        def is_comfortable(dewp: float, ssi: float, rel_hum: float) -> bool:
            return (
                rel_hum <= self._humidity_max
                and ssi <= self._ssi_comfort_max
                and dewp <= self._dewp_comfort_max
            )

        comfort_list: list[bool] = []
        ssi_list: list[float] = []
        temp_unit = self._temp_unit

        # TODO: skip outdated entries and only take next 24 hours
        for entry in forecast:
            dewp = dew_point(entry.temp, entry.humidity, temp_unit)
            ssi = simmer_index(entry.temp, entry.humidity, temp_unit)
            comfort_list.append(is_comfortable(dewp, ssi, entry.humidity))
            ssi_list.append(ssi)

        in_dewp = dew_point(in_temperature, in_humidity, temp_unit)
        in_ssi = simmer_index(in_temperature, in_humidity, temp_unit)
        out_dewp = dew_point(out_temperature, out_humidity, temp_unit)
        out_ssi = simmer_index(out_temperature, out_humidity, temp_unit)
        max_ssi = max(ssi_list) if ssi_list else None

        open_windows, open_windows_reason = (
            (False, "in_better")
            if out_ssi > in_ssi or out_dewp > in_dewp
            else (False, "out_ssi_high")
            if out_ssi > self._ssi_comfort_max
            else (False, "out_humidity_high")
            if out_dewp > self._dewp_comfort_max or out_humidity > self._humidity_max
            else (False, "out_forecast_cool")
            if in_ssi <= self._ssi_comfort_max
            and (max_ssi is None or max_ssi <= self._ssi_comfort_min)
            else (True, "out_better")
        )

        self.states.update(
            {
                DeviceState.OPEN_WINDOWS: open_windows,
                DeviceState.OPEN_WINDOWS_REASON: open_windows_reason,
            }
        )

        self.extra_state_attributes.update(
            {
                "inside_dew_point": in_dewp,
                "inside_simmer_index": in_ssi,
                "outside_dew_point": out_dewp,
                "outside_simmer_index": out_ssi,
            }
        )

        return True

        # TODO: calculate time of next change
        # from datetime import timedelta
        # from itertools import takewhile
        # self.time_until_change = len(
        #    list(takewhile(lambda x: x == self.open_windows, hourly_comfort))
        # )
