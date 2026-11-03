"""Device for comfort_advisor."""

from collections.abc import Callable, Mapping
import contextlib
from datetime import datetime
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
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_state_change_event,
)
from homeassistant.util.json import JsonValueType
from homeassistant.util.unit_conversion import TemperatureConverter as TC

from .comfort import ComfortCalculator, Input, pollen_level
from .const import (
    _LOGGER,
    CONF_INDOOR_HUMIDITY,
    CONF_INDOOR_TEMPERATURE,
    CONF_POLLEN,
    CONF_WEATHER,
    DEFAULT_MANUFACTURER,
    DEFAULT_NAME,
    DOMAIN,
    INPUT_COOLDOWN,
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
        self._listeners: list[Callable[[], None]] = []
        self._debouncer = Debouncer(
            hass, _LOGGER, cooldown=INPUT_COOLDOWN, immediate=False, function=self._refresh
        )
        self._expiry_timer: CALLBACK_TYPE | None = None
        self._expiry_timer_at: datetime | None = None

        self._entity_id_to_input: dict[str, Input] = {
            self._config[input]: input
            for input in [
                Input.INDOOR_TEMPERATURE,
                Input.INDOOR_HUMIDITY,
                Input.OUTDOOR_TEMPERATURE,
                Input.OUTDOOR_HUMIDITY,
            ]
        }
        self._pollen_entity_ids: list[str] = list(self._config.get(CONF_POLLEN, []))

    async def async_setup_entry(self, config_entry: ConfigEntry) -> None:
        """Subscribe to the weather forecast and input sensors.

        Raises ConfigEntryNotReady (so Home Assistant retries) when the weather
        entity doesn't exist yet, e.g. its integration is still starting.
        """

        @callback
        def forecast_listener(forecast: list[JsonValueType] | None) -> None:
            self._comfort.update_input(Input.FORECAST, forecast or None)
            self._debouncer.async_schedule_call()

        weather_entity_id = self._config[CONF_WEATHER]
        unsubscribe = await async_subscribe_forecast(
            self.hass, weather_entity_id, "hourly", forecast_listener
        )
        if unsubscribe is None:
            raise ConfigEntryNotReady(
                translation_domain=DOMAIN,
                translation_key="weather_not_found",
                translation_placeholders={"entity_id": weather_entity_id},
            )

        config_entry.async_on_unload(unsubscribe)

        config_entry.async_on_unload(
            async_track_state_change_event(
                self.hass, self._entity_id_to_input.keys(), self._input_event_handler
            )
        )
        if self._pollen_entity_ids:
            config_entry.async_on_unload(
                async_track_state_change_event(
                    self.hass, self._pollen_entity_ids, self._pollen_event_handler
                )
            )

        config_entry.async_on_unload(self._cancel_expiry_timer)
        config_entry.async_on_unload(self._debouncer.async_shutdown)

        for entity_id in self._entity_id_to_input:
            self._update_input_from_state(entity_id, self.hass.states.get(entity_id))
        self._update_pollen()

        # Calculate now so the sensors start with values.
        self._debouncer.async_cancel()
        self._refresh()

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

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        """Call `listener` whenever the calculated state changes; return a remover."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    # Internal methods

    @callback
    def _input_event_handler(self, event: Event[EventStateChangedData]) -> None:
        self._update_input_from_state(event.data["entity_id"], event.data["new_state"])

    @callback
    def _pollen_event_handler(self, _: Event[EventStateChangedData]) -> None:
        self._update_pollen()
        self._debouncer.async_schedule_call()

    def _update_pollen(self) -> None:
        """Feed the highest level of the pollen sensors that have one.

        Pollen is optional: sensors without a usable level (unavailable,
        unknown or unrecognized) are left out rather than clearing the outputs.
        """
        levels = [
            level
            for entity_id in self._pollen_entity_ids
            if (state := self.hass.states.get(entity_id))
            and (level := pollen_level(state.state)) is not None
        ]
        self._comfort.update_pollen(max(levels, default=None))

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
        self._debouncer.async_schedule_call()

    @staticmethod
    def _get_state_value(state: State) -> float | None:
        with contextlib.suppress(ValueError):
            value = float(state.state)
            if not math.isnan(value):
                return value
        return None

    @callback
    def _refresh(self) -> None:
        """Recalculate if needed, notify listeners, and schedule the next expiry."""
        if self._comfort.refresh_state():
            for listener in list(self._listeners):
                listener()

        expires_at = self._comfort.expires_at
        if expires_at != self._expiry_timer_at:
            self._cancel_expiry_timer()
            if expires_at is not None:
                self._expiry_timer = async_track_point_in_utc_time(
                    self.hass, self._handle_expiry, expires_at
                )
                self._expiry_timer_at = expires_at

    @callback
    def _handle_expiry(self, _: datetime) -> None:
        self._expiry_timer = None
        self._expiry_timer_at = None
        self._refresh()

    @callback
    def _cancel_expiry_timer(self) -> None:
        if self._expiry_timer:
            self._expiry_timer()
        self._expiry_timer = None
        self._expiry_timer_at = None
