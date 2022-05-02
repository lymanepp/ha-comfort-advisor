"""Device for comfort_advisor."""
from __future__ import annotations

from datetime import datetime, timedelta
import math
from typing import Any, TypedDict, cast

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ATTRIBUTION,
    ATTR_DEVICE_CLASS,
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
from homeassistant.util.temperature import convert as convert_temp

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


class _CalculatedState(TypedDict, total=False):
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
        self._inputs: dict[str, Any] = {}
        self._calculated = _CalculatedState()

        self.should_poll = self._config[CONF_DEVICE][CONF_POLL]
        self._extra_state_attributes: dict[str, Any] = {ATTR_ATTRIBUTION: provider.attribution}

        config_entry.async_on_unload(
            self._realtime_service.async_add_listener(self._realtime_updated)
        )
        config_entry.async_on_unload(
            self._forecast_service.async_add_listener(self._forecast_updated)
        )

        self._entity_id_map: dict[str, list[str]] = {}

        for input_key in [
            CONF_INDOOR_TEMPERATURE,
            CONF_INDOOR_HUMIDITY,
            CONF_OUTDOOR_TEMPERATURE,
            CONF_OUTDOOR_HUMIDITY,
        ]:
            entity_id = self._config[CONF_INPUTS][input_key]
            # creating a list allows a sensor to be used multiple times
            # TODO: prevent that in config_flow when done testing
            self._entity_id_map.setdefault(entity_id, []).append(input_key)

        config_entry.async_on_unload(
            async_track_state_change_event(
                self.hass, self._entity_id_map.keys(), self._event_handler
            )
        )

        hass.async_create_task(self._set_sw_version())

        if self.should_poll:  # TODO: this blows up if enabled
            async_track_time_interval(
                self.hass,
                self._async_update_entities,
                self._config.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
            )

    @property
    def name(self) -> str:
        """Return the name."""
        return cast(str, self.device_info["name"])

    @property
    def calculated(self) -> _CalculatedState:
        """Return the calculated state."""
        return self._calculated

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the extra device attributes."""
        return self._extra_state_attributes

    def add_entity(self, entity: Entity) -> CALLBACK_TYPE:
        """Add entity to receive callback when the calculated state is updated."""
        self._entities.append(entity)
        return lambda: self._entities.remove(entity)

    # Internal methods

    async def _set_sw_version(self) -> None:
        custom_components = await async_get_custom_components(self.hass)
        self.device_info["sw_version"] = custom_components[DOMAIN].version.string

    def _realtime_updated(self) -> None:
        self._inputs["realtime"] = self._realtime_service.data
        self.hass.async_create_task(self._async_update())  # run in event loop

    def _forecast_updated(self) -> None:
        self._inputs["forecast"] = self._forecast_service.data
        self.hass.async_create_task(self._async_update())  # run in event loop

    async def _event_handler(self, event: Event) -> None:
        state: State = event.data.get("new_state")
        if state.state in (None, STATE_UNKNOWN, STATE_UNAVAILABLE):
            return
        try:
            value = float(state.state)
        except ValueError:
            return
        if math.isnan(value):
            return

        device_class: str = state.attributes.get(ATTR_DEVICE_CLASS)
        if device_class == SensorDeviceClass.TEMPERATURE:
            unit: str = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
            if unit and unit != self._temp_unit:
                value = convert_temp(value, unit, self._temp_unit)

        # TODO: remove when list isn't supported
        for input_key in self._entity_id_map[event.data["entity_id"]]:
            self._inputs[input_key] = value
        await self._async_update()

    async def _async_update(self) -> None:
        if not self.should_poll:
            await self._async_update_entities(force_refresh=True)

    async def _async_update_entities(self, force_refresh: bool = False) -> None:
        if self._calculate_state(**(self._config[CONF_COMFORT]), **(self._inputs)):
            for entity in self._entities:
                entity.async_schedule_update_ha_state(force_refresh)

    def _calculate_state(  # type: ignore
        self,
        *,
        # config values
        dew_point_max: float,
        humidity_max: float,
        simmer_index_min: float,
        simmer_index_max: float,
        pollen_max: int,
        # input values
        indoor_temperature: float | None = None,
        indoor_humidity: float | None = None,
        outdoor_temperature: float | None = None,
        outdoor_humidity: float | None = None,
        realtime: WeatherData | None = None,
        forecast: list[WeatherData] | None = None,
    ) -> bool:
        if (
            indoor_temperature is None
            or indoor_humidity is None
            or outdoor_temperature is None
            or outdoor_humidity is None
        ):
            return False

        def calc(temp: float, humidity: float, pollen: int) -> tuple[bool, float, float]:
            dew_point = compute_dew_point(temp, humidity, temp_unit)
            simmer_index = compute_simmer_index(temp, humidity, temp_unit)
            is_comfortable = (
                humidity <= humidity_max
                and simmer_index_min <= simmer_index <= simmer_index_max
                and dew_point <= dew_point_max
                and pollen <= pollen_max
            )
            return is_comfortable, dew_point, simmer_index

        temp_unit = self._temp_unit
        outdoor_pollen = (realtime.pollen if realtime else None) or 0

        _, in_dewp, in_si = calc(indoor_temperature, indoor_humidity, 0)
        out_comfort, out_dewp, out_si = calc(outdoor_temperature, outdoor_humidity, outdoor_pollen)

        start_time = utcnow()
        end_time = start_time + timedelta(days=1)

        next_change_time: datetime | None = None
        high_si = out_si

        for entry in forecast or []:
            if entry.date_time < start_time:
                continue
            comfort, _, si = calc(entry.temp, entry.humidity, entry.pollen or 0)
            if next_change_time is None and comfort != out_comfort:
                next_change_time = entry.date_time
            if entry.date_time <= end_time:
                high_si = max(high_si, si)

        self._calculated.update(
            {
                STATE_HIGH_SIMMER_INDEX: high_si,
                STATE_NEXT_CHANGE_TIME: next_change_time,
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
