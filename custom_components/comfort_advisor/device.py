"""Device for comfort_advisor."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
import math
from typing import Any, Mapping, Sequence, TypedDict, cast

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
    DOMAIN,
    STATE_CAN_OPEN_WINDOWS,
)
from .formulas import compute_dew_point, compute_simmer_index
from .provider import Provider, WeatherData

_LOGGER = logging.getLogger(__name__)

ATTR_INDOOR_DEW_POINT = "indoor_dew_point"
ATTR_INDOOR_SIMMER_INDEX = "indoor_simmer_index"
ATTR_OUTDOOR_DEW_POINT = "outdoor_dew_point"
ATTR_OUTDOOR_SIMMER_INDEX = "outdoor_simmer_index"

NO_YES = ["no", "yes"]


class _CalculatedState(TypedDict, total=False):
    """TODO."""

    can_open_windows: str | None
    low_simmer_index: float | None
    high_simmer_index: float | None
    next_change_time: datetime | None


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
        self.device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, self.unique_id)},
            manufacturer=DEFAULT_MANUFACTURER,
            model=DEFAULT_NAME,
            name=self._config[CONF_DEVICE][CONF_NAME],
            hw_version=provider.version,
        )

        self._provider = provider
        self._temp_unit = self.hass.config.units.temperature_unit  # TODO: add config entry?
        self._entities: list[Entity] = []
        self._inputs: dict[str, Any] = {}
        self._calculated = _CalculatedState()
        self._have_changes = False

        self._polling = self._config[CONF_DEVICE][CONF_POLL]
        self._extra_state_attributes: dict[str, Any] = {ATTR_ATTRIBUTION: provider.attribution}

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
            if (state := self.hass.states.get(entity_id)) is not None:
                self._process_state_change(state)

        if self._polling:
            poll_interval = self._config[CONF_DEVICE][CONF_POLL_INTERVAL]
            config_entry.async_on_unload(
                async_track_time_interval(
                    self.hass,
                    self._async_update_scheduled,
                    timedelta(seconds=poll_interval),
                )
            )

        self.hass.async_create_task(self._set_sw_version())
        return True

    @property
    def name(self) -> str:
        """Return the name."""
        return cast(str, self.device_info["name"])

    @property
    def calculated(self) -> _CalculatedState:
        """Return the calculated state."""
        return self._calculated

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
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
        if self._update_input_value("realtime", self._provider.realtime_service.data):
            if not self._polling:
                self.hass.async_create_task(self._async_update())  # run in event loop

    def _forecast_updated(self) -> None:
        if self._update_input_value("forecast", self._provider.forecast_service.data):
            if not self._polling:
                self.hass.async_create_task(self._async_update())  # run in event loop

    async def _input_event_handler(self, event: Event) -> None:
        state: State = event.data.get("new_state")
        _LOGGER.debug(
            "_event_handler called for %s - entity(%s) - state(%s)",
            self.device_info["name"],
            state.entity_id if state else None,
            state.state if state else None,
        )
        if self._process_state_change(state):
            if not self._polling:
                await self._async_update(force_refresh=False)

    def _process_state_change(self, state: State) -> bool:
        _LOGGER.debug(
            "_update_input_state called for %s - entity(%s) - state(%s)",
            self.device_info["name"],
            state.entity_id if state else None,
            state.state if state else None,
        )
        if state is None or state.state in (None, STATE_UNKNOWN, STATE_UNAVAILABLE):
            return False
        try:
            value = float(state.state)
        except ValueError:
            return False
        if math.isnan(value):
            return False

        device_class: str = state.attributes.get(ATTR_DEVICE_CLASS)
        if device_class == SensorDeviceClass.TEMPERATURE:
            unit: str = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
            if unit and unit != self._temp_unit:
                value = convert_temp(value, unit, self._temp_unit)

        for input_key in self._entity_id_map[state.entity_id]:
            self._update_input_value(input_key, value)
        return True

    def _update_input_value(self, input_key: str, value: Any) -> bool:
        _LOGGER.debug("%s updated %s to %s", self.device_info["name"], input_key, str(value))
        if self._inputs.get(input_key) != value:
            self._inputs[input_key] = value
            self._have_changes = True
            return True
        return False

    # `async_track_time_interval` adds a `now` arg that must be stripped
    async def _async_update_scheduled(self, now: datetime) -> None:
        await self._async_update()

    async def _async_update(self, force_refresh: bool = True) -> None:
        _LOGGER.debug(
            "_async_update called for %s force_refresh=%s",
            self.device_info["name"],
            str(force_refresh),
        )
        if self._have_changes:
            # TODO: do this on task instead of in event loop?
            if self._calculate_state(**(self._config[CONF_COMFORT]), **(self._inputs)):
                for entity in self._entities:
                    entity.async_schedule_update_ha_state(force_refresh)
            self._have_changes = False

    def _calculate_state(
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
        forecast: Sequence[WeatherData] | None = None,
    ) -> bool:
        _LOGGER.debug("_calculate_state called for %s", self.device_info["name"])
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

        self._extra_state_attributes.update(
            {
                ATTR_INDOOR_DEW_POINT: in_dewp,
                ATTR_INDOOR_SIMMER_INDEX: in_si,
                ATTR_OUTDOOR_DEW_POINT: out_dewp,
                ATTR_OUTDOOR_SIMMER_INDEX: out_si,
            }
        )

        self._calculated[STATE_CAN_OPEN_WINDOWS] = NO_YES[out_comfort]

        if forecast:
            start_time = utcnow()
            end_time = start_time + timedelta(days=1)

            next_change_time: datetime | None = None
            high_si = low_si = out_si

            for interval in filter(lambda x: x.date_time >= start_time, forecast):
                comfort, _, si = calc(interval.temp, interval.humidity, interval.pollen or 0)
                if next_change_time is None and comfort != out_comfort:
                    next_change_time = interval.date_time
                if interval.date_time <= end_time:
                    low_si = min(low_si, si)
                    high_si = max(high_si, si)

            self._calculated["low_simmer_index"] = low_si
            self._calculated["high_simmer_index"] = high_si
            self._calculated["next_change_time"] = next_change_time

        # TODO: create blueprint that uses `next_change_time` if windows can be open "all night"?
        # TODO: blueprint checks `high_simmer_index` if it will be cool tomorrow and conserve heat
        # TODO: need to check when `si_list` will be higher than `in_si`
        # TODO: create `comfort score` and create sensor for that?

        return True
