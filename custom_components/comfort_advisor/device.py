"""Device for comfort_advisor."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from typing import Any, TypedDict, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ATTRIBUTION,
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_NAME,
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
from homeassistant.util.dt import utcnow

from .const import (
    CONF_COMFORT,
    CONF_DEVICE,
    CONF_INDOOR_HUMIDITY,
    CONF_INDOOR_TEMPERATURE,
    CONF_INPUTS,
    CONF_OUTDOOR_HUMIDITY,
    CONF_OUTDOOR_TEMPERATURE,
    CONF_POLL,
    CONF_POLL_INTERVAL,
    DEFAULT_MANUFACTURER,
    DEFAULT_NAME,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    STATE_HIGH_SIMMER_INDEX,
    STATE_NEXT_CHANGE_TIME,
    STATE_OPEN_WINDOWS,
)
from .formulas import compute_dew_point, compute_simmer_index
from .provider import Provider, WeatherData

ATTR_INDOOR_DEW_POINT = "indoor_dew_point"
ATTR_INDOOR_SIMMER_INDEX = "indoor_simmer_index"
ATTR_OUTDOOR_DEW_POINT = "outdoor_dew_point"
ATTR_OUTDOOR_SIMMER_INDEX = "outdoor_simmer_index"


@dataclass
class DeviceInputs:
    """The device state."""

    # weather provider
    realtime: WeatherData = None  # type: ignore
    forecast: list[WeatherData] = None  # type: ignore

    # input sensors
    indoor_temp: float = None  # type: ignore
    indoor_humidity: float = None  # type: ignore
    outdoor_temp: float = None  # type: ignore
    outdoor_humidity: float = None  # type: ignore
    outdoor_pollen: int = None  # type: ignore


class DeviceState(TypedDict, total=False):
    """TODO."""

    open_windows: bool | None
    open_windows_reason: str | None
    high_simmer_index: float | None
    next_change_time: datetime | None


class ComfortAdvisorDevice:
    """Representation of a Comfort Advisor Device."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        provider: Provider,
        realtime_service: DataUpdateCoordinator[WeatherData],
        forecast_service: DataUpdateCoordinator[list[WeatherData]],
    ) -> None:
        """Initialize the device."""
        self._config = config_entry.data | config_entry.options or {}
        self.hass = hass
        self.unique_id = config_entry.unique_id
        self.device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, self.unique_id)},
            manufacturer=DEFAULT_MANUFACTURER,
            model=DEFAULT_NAME,
            name=self._config[CONF_DEVICE][CONF_NAME],
            hw_version=provider.version,
        )

        self._temp_unit = self.hass.config.units.temperature_unit  # TODO: add config entry?
        self._realtime_service = realtime_service
        self._forecast_service = forecast_service
        self._entities: list[Entity] = []
        self._inputs = DeviceInputs()
        self._state = DeviceState()

        self.should_poll = self._config[CONF_DEVICE][CONF_POLL]
        self._extra_state_attributes: dict[str, Any] = {ATTR_ATTRIBUTION: provider.attribution}

        config_entry.async_on_unload(
            self._realtime_service.async_add_listener(self._realtime_updated)
        )
        config_entry.async_on_unload(
            self._forecast_service.async_add_listener(self._forecast_updated)
        )

        # TODO: need common listener that updates the right state bucket
        for config_key, listener in (
            (CONF_INDOOR_TEMPERATURE, self._in_temp_listener),
            (CONF_INDOOR_HUMIDITY, self._in_humidity_listener),
            (CONF_OUTDOOR_TEMPERATURE, self._out_temp_listener),
            (CONF_OUTDOOR_HUMIDITY, self._out_humidity_listener),
        ):
            if entity_id := self._config[CONF_INPUTS].get(config_key):
                config_entry.async_on_unload(
                    async_track_state_change_event(self.hass, entity_id, listener)
                )

        hass.async_create_task(self._set_sw_version())

        if self.should_poll:  # TODO: this blows up if enabled
            async_track_time_interval(
                self.hass,
                self.async_update_entities,
                self._config.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
            )

    @property
    def state(self) -> DeviceState:
        """TODO."""
        return self._state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """TODO."""
        return self._extra_state_attributes

    def add_entity(self, entity: Entity) -> CALLBACK_TYPE:
        """TODO."""
        self._entities.append(entity)
        return lambda: self._entities.remove(entity)

    async def _set_sw_version(self) -> None:
        custom_components = await async_get_custom_components(self.hass)
        self.device_info["sw_version"] = custom_components[DOMAIN].version.string

    def _realtime_updated(self) -> None:
        self._inputs.realtime = self._realtime_service.data
        self.hass.async_create_task(self.async_update())  # run in event loop

    def _forecast_updated(self) -> None:
        self._inputs.forecast = self._forecast_service.data
        self.hass.async_create_task(self.async_update())  # run in event loop

    async def _in_temp_listener(self, event: Event) -> None:
        if (state := self._get_new_state(event)) is not None:
            self._inputs.indoor_temp = self._get_temp(state)
            await self.async_update()

    async def _in_humidity_listener(self, event: Event) -> None:
        if (state := self._get_new_state(event)) is not None:
            self._inputs.indoor_humidity = float(state.state)
            await self.async_update()

    async def _out_temp_listener(self, event: Event) -> None:
        if (state := self._get_new_state(event)) is not None:
            self._inputs.outdoor_temp = self._get_temp(state)
            await self.async_update()

    async def _out_humidity_listener(self, event: Event) -> None:
        if (state := self._get_new_state(event)) is not None:
            self._inputs.outdoor_humidity = float(state.state)
            await self.async_update()

    async def _out_pollen_listener(self, event: Event) -> None:
        if (state := self._get_new_state(event)) is not None:
            self._inputs.outdoor_pollen = state.state  # TODO
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
        if not self.should_poll:
            await self.async_update_entities(force_refresh=True)

    async def async_update_entities(self, force_refresh: bool = False) -> None:
        """Update the state of the entities."""
        if self._calculate_state(**(self._config[CONF_COMFORT])):
            for entity in self._entities:
                entity.async_schedule_update_ha_state(force_refresh)

    @property
    def name(self) -> str:
        """Return the name."""
        return cast(str, self.device_info["name"])

    def _calculate_state(  # type: ignore
        self,
        *,
        dew_point_max: float,
        humidity_max: float,
        simmer_index_min: float,
        simmer_index_max: float,
        pollen_max: int,
        **kwargs,
    ) -> bool:
        inputs = self._inputs
        if (
            inputs.indoor_temp is None
            or inputs.indoor_humidity is None
            or inputs.outdoor_temp is None
            or inputs.outdoor_humidity is None
        ):
            return False

        def calc(temp: float, humidity: float, pollen: int) -> tuple[bool, float, float]:
            dewp = compute_dew_point(temp, humidity, temp_unit)
            si = compute_simmer_index(temp, humidity, temp_unit)
            comfortable = (
                humidity <= humidity_max
                and simmer_index_min <= si <= simmer_index_max
                and dewp <= dew_point_max
                and pollen <= pollen_max
            )
            return comfortable, dewp, si

        temp_unit = self._temp_unit
        pollen = inputs.outdoor_pollen or 0

        _, in_dewp, in_si = calc(inputs.indoor_temp, inputs.indoor_humidity, 0)
        out_comfort, out_dewp, out_si = calc(inputs.indoor_temp, inputs.indoor_humidity, pollen)

        comfort_list: list[bool] = []
        si_list: list[float] = []
        start = utcnow()
        end = start + timedelta(days=1)
        next_day = list(filter(lambda x: start <= x.date_time <= end, inputs.forecast or []))

        for entry in next_day:
            comfort, _, si = calc(entry.temp, entry.humidity, entry.pollen or 0)
            comfort_list.append(comfort)
            si_list.append(si)

        change_ndx = next((ndx for ndx, x in enumerate(comfort_list) if x != out_comfort), None)

        self._state.update(
            {
                STATE_HIGH_SIMMER_INDEX: max(si_list) if si_list else None,
                STATE_NEXT_CHANGE_TIME: next_day[change_ndx].date_time if change_ndx else None,  # type: ignore
                STATE_OPEN_WINDOWS: out_comfort,
            }
        )
        self._extra_state_attributes.update(
            {
                ATTR_INDOOR_DEW_POINT: in_dewp,
                ATTR_INDOOR_SIMMER_INDEX: in_si,
                ATTR_OUTDOOR_DEW_POINT: out_dewp,
                ATTR_OUTDOOR_SIMMER_INDEX: out_si,
            }
        )

        # TODO: create blueprint that uses `next_change_time` if windows can be open "all night"?
        # TODO: blueprint checks `high_simmer_index` if it will be cool tomorrow and conserve heat
        # TODO: need to check when `si_list` will be higher than `in_si`
        # TODO: create `comfort score` and create sensor for that?

        return True
