"""TODO."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import dropwhile, takewhile
import logging
from typing import Any, Iterable, Mapping, Sequence

from homeassistant.backports.enum import StrEnum
from homeassistant.const import CONF_TEMPERATURE_UNIT
from homeassistant.util.dt import utcnow
from homeassistant.util.unit_conversion import TemperatureConverter as TC

from .const import (
    CONF_DEW_POINT_MAX,
    CONF_HUMIDITY_MAX,
    CONF_POLLEN_MAX,
    CONF_SIMMER_INDEX_MAX,
    CONF_SIMMER_INDEX_MIN,
)
from .formulas import compute_dew_point, compute_moist_air_enthalpy, compute_simmer_index
from .provider import WeatherData

_LOGGER = logging.getLogger(__name__)


class Input(StrEnum):  # type: ignore
    """ComfortCalculator inputs."""

    REALTIME = "realtime"
    FORECAST = "forecast"
    INDOOR_TEMPERATURE = "indoor_temperature"
    INDOOR_HUMIDITY = "indoor_humidity"
    OUTDOOR_TEMPERATURE = "outdoor_temperature"
    OUTDOOR_HUMIDITY = "outdoor_humidity"


class State(StrEnum):  # type: ignore
    """ComfortCalculator states."""

    CAN_OPEN_WINDOWS = "can_open_windows"
    OPEN_WINDOWS_AT = "open_windows_at"
    CLOSE_WINDOWS_AT = "close_windows_at"
    LOW_SIMMER_INDEX = "low_simmer_index"
    HIGH_SIMMER_INDEX = "high_simmer_index"


@dataclass
class ComfortData(WeatherData):
    """Data format returned by weather provider."""

    dew_point: float
    simmer_index: float
    comfortable: bool | None

    @classmethod
    def from_weather_data(cls, other: WeatherData, temp_unit: str) -> ComfortData:
        """Create `ComfortData` from `WeatherData`."""
        return cls(
            date_time=other.date_time,
            temp=other.temp,
            humidity=other.humidity,
            wind_speed=other.wind_speed,
            pollen=other.pollen,
            dew_point=compute_dew_point(other.temp, other.humidity, temp_unit),
            simmer_index=compute_simmer_index(other.temp, other.humidity, temp_unit),
            comfortable=None,
        )


# ATTR_INDOOR_DEW_POINT = "indoor_dew_point"
# ATTR_INDOOR_SIMMER_INDEX = "indoor_simmer_index"
# ATTR_OUTDOOR_DEW_POINT = "outdoor_dew_point"
# ATTR_OUTDOOR_SIMMER_INDEX = "outdoor_simmer_index"
# ATTR_POLLEN = "pollen"


class ComfortCalculator:
    """Calculate comfort states."""

    def __init__(self, hass_temp_unit: str, config: Mapping[str, Any]) -> None:
        """Initialize."""

        # The temperature unit is stored with configuration just in case the unit
        # system is changed later. Convert units to the current unit system.
        config_temp_unit = config[CONF_TEMPERATURE_UNIT]
        self._dew_point_max = TC.convert(
            config[CONF_DEW_POINT_MAX], config_temp_unit, hass_temp_unit
        )
        self._simmer_index_min = TC.convert(
            config[CONF_SIMMER_INDEX_MIN], config_temp_unit, hass_temp_unit
        )
        self._simmer_index_max = TC.convert(
            config[CONF_SIMMER_INDEX_MAX], config_temp_unit, hass_temp_unit
        )

        self._humidity_max: float = config[CONF_HUMIDITY_MAX]
        self._pollen_max: int = config[CONF_POLLEN_MAX]
        self._temp_unit = hass_temp_unit

        # state
        self._have_changes = False
        self._inputs: dict[str, Any] = {str(x): None for x in Input}  # type: ignore
        self._state: dict[str, Any] = {str(x): None for x in State}  # type: ignore
        self._extra_attributes: dict[str, Any] = {}

    @property
    def extra_attributes(self) -> Mapping[str, Any]:
        """Return extra attributes."""
        return self._extra_attributes

    def update_input(self, key: str, value: Any) -> None:
        """Update an input value."""
        _LOGGER.debug("update_input called with %s=%s", key, str(value))
        if value is None or self._inputs[key] == value:
            return

        if key == Input.FORECAST and isinstance(value, Iterable):
            # augment forecast with psychrometrics
            value = [ComfortData.from_weather_data(x, self._temp_unit) for x in value if x]

        self._inputs[key] = value
        self._have_changes = True

    def get_state(self, name: str, default: Any = None) -> Any:
        """Retrieve a calculated state."""
        return self._state.get(name, default)

    def refresh_state(self) -> bool:
        """Refresh the calculated state."""
        if not self._have_changes:
            return False
        self._have_changes = False

        if any(value is None for value in self._inputs.values()):
            return False

        realtime: WeatherData = self._inputs[Input.REALTIME]
        forecast: Sequence[ComfortData] = self._inputs[Input.FORECAST]
        in_temp: float = self._inputs[Input.INDOOR_TEMPERATURE]
        in_humidity: float = self._inputs[Input.INDOOR_HUMIDITY]
        out_temp: float = self._inputs[Input.OUTDOOR_TEMPERATURE]
        out_humidity: float = self._inputs[Input.OUTDOOR_HUMIDITY]

        # in_dewp = compute_dew_point(in_temp, in_humidity, self._temp_unit)
        # in_ssi = compute_simmer_index(in_temp, in_humidity, self._temp_unit)
        in_enthalpy = compute_moist_air_enthalpy(in_temp, in_humidity, self._temp_unit)
        out_dewp = compute_dew_point(out_temp, out_humidity, self._temp_unit)
        out_ssi = compute_simmer_index(out_temp, out_humidity, self._temp_unit)
        out_enthalpy = compute_moist_air_enthalpy(out_temp, out_humidity, self._temp_unit)

        start_time = utcnow()
        future_data = list(dropwhile(lambda x: x.date_time <= start_time, forecast))
        end_time = start_time + timedelta(days=1)
        next_24 = list(takewhile(lambda x: x.date_time <= end_time, future_data))

        low_simmer_index = min(x.simmer_index for x in next_24) if next_24 else None
        high_simmer_index = max(x.simmer_index for x in next_24) if next_24 else None

        def is_comfortable(
            humidity: float, dew_point: float, simmer_index: float, pollen: int
        ) -> bool:
            return (
                simmer_index <= self._simmer_index_max
                and (
                    simmer_index >= self._simmer_index_min
                    or (
                        high_simmer_index is not None and high_simmer_index > self._simmer_index_max
                    )
                )
                and dew_point <= self._dew_point_max
                and humidity <= self._humidity_max
                and pollen <= self._pollen_max
            )

        comfortable_now = (
            is_comfortable(out_humidity, out_dewp, out_ssi, realtime.pollen or 0)
            and out_enthalpy <= in_enthalpy
        )

        for period in next_24:
            period.comfortable = is_comfortable(
                period.humidity, period.dew_point, period.simmer_index, period.pollen or 0
            )

        first_time: datetime | None = None
        second_time: datetime | None = None

        if change := list(dropwhile(lambda x: x.comfortable == comfortable_now, next_24)):
            first_time = change[0].date_time

            uncomfortable_now = not comfortable_now
            if change := list(dropwhile(lambda x: x.comfortable == uncomfortable_now, change)):
                second_time = change[0].date_time

        self._state[State.CAN_OPEN_WINDOWS] = ["off", "on"][comfortable_now]
        self._state[State.LOW_SIMMER_INDEX] = low_simmer_index
        self._state[State.HIGH_SIMMER_INDEX] = high_simmer_index
        self._state[State.OPEN_WINDOWS_AT] = second_time if comfortable_now else first_time
        self._state[State.CLOSE_WINDOWS_AT] = first_time if comfortable_now else second_time

        # self._extra_attributes = {
        #    ATTR_INDOOR_DEW_POINT: in_dewp,
        #    ATTR_INDOOR_SIMMER_INDEX: in_ssi,
        #    ATTR_OUTDOOR_DEW_POINT: out_dewp,
        #    ATTR_OUTDOOR_SIMMER_INDEX: out_si,
        # }

        # if realtime and realtime.pollen is not None:
        #    self._extra_attributes[ATTR_POLLEN] = realtime.pollen

        return True

        # TODO: create blueprint that uses `next_change_time` if windows can be open "all night"?
        # TODO: blueprint checks `high_simmer_index` if it will be cool tomorrow and conserve heat
        # TODO: need to check when `si_list` will be higher than `in_ssi`
        # TODO: create `comfort score` and create sensor for that?
        # TODO: check if temperature forecast is rising or falling currently
