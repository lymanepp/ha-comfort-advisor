"""TODO."""

from datetime import datetime, timedelta
import logging
from typing import Any, Mapping, Sequence

from homeassistant.backports.enum import StrEnum
from homeassistant.util.dt import utcnow

from .const import (
    CONF_DEW_POINT_MAX,
    CONF_HUMIDITY_MAX,
    CONF_POLLEN_MAX,
    CONF_SIMMER_INDEX_MAX,
    CONF_SIMMER_INDEX_MIN,
)
from .formulas import compute_dew_point, compute_simmer_index
from .provider import WeatherData

_LOGGER = logging.getLogger(__name__)


class Input(StrEnum):  # type: ignore
    """TODO."""

    REALTIME = "realtime"
    FORECAST = "forecast"
    INDOOR_TEMPERATURE = "indoor_temperature"
    INDOOR_HUMIDITY = "indoor_humidity"
    OUTDOOR_TEMPERATURE = "outdoor_temperature"
    OUTDOOR_HUMIDITY = "outdoor_humidity"


class State(StrEnum):  # type: ignore
    """TODO."""

    CAN_OPEN_WINDOWS = "can_open_windows"
    LOW_SIMMER_INDEX = "low_simmer_index"
    HIGH_SIMMER_INDEX = "high_simmer_index"
    NEXT_CHANGE_TIME = "next_change_time"


class Attrib(StrEnum):  # type:ignore
    """TODO."""

    INDOOR_DEW_POINT = "indoor_dew_point"
    INDOOR_SIMMER_INDEX = "indoor_simmer_index"
    OUTDOOR_DEW_POINT = "outdoor_dew_point"
    OUTDOOR_SIMMER_INDEX = "outdoor_simmer_index"


class ComfortThingy:
    """TODO."""

    def __init__(self, temp_unit: str, config: Mapping[str, Any]) -> None:
        """TODO."""
        self._temp_unit = temp_unit

        # configuration
        self._dew_point_max = config[CONF_DEW_POINT_MAX]
        self._humidity_max = config[CONF_HUMIDITY_MAX]
        self._simmer_index_min = config[CONF_SIMMER_INDEX_MIN]
        self._simmer_index_max = config[CONF_SIMMER_INDEX_MAX]
        self._pollen_max = config[CONF_POLLEN_MAX]

        # state
        self._inputs: dict[str, Any] = {str(x): None for x in Input}  # type: ignore
        self._state: dict[str, Any] = {str(x): None for x in State}  # type: ignore
        self._have_changes: bool = False
        self._extra_attributes: dict[str, Any] = {}

    @property
    def extra_attributes(self) -> Mapping[str, Any]:
        """TODO."""
        return self._extra_attributes

    def update_input(self, name: str, value: Any) -> None:
        """TODO."""
        if self._inputs[name] != value:
            self._inputs[name] = value
            self._have_changes = True

    def get_state(self, name: str, default: Any = None) -> Any:
        """TODO."""
        return self._state.get(name, default)

    def refresh_state(self) -> bool:
        """TODO."""
        if not self._have_changes:
            return False
        self._have_changes = False

        _LOGGER.debug("_calculate_state called for %s", "TODO")

        indoor_temperature: float | None = self._inputs[Input.INDOOR_TEMPERATURE]
        indoor_humidity: float | None = self._inputs[Input.INDOOR_HUMIDITY]
        outdoor_temperature: float | None = self._inputs[Input.OUTDOOR_TEMPERATURE]
        outdoor_humidity: float | None = self._inputs[Input.OUTDOOR_HUMIDITY]

        if (
            indoor_temperature is None
            or indoor_humidity is None
            or outdoor_temperature is None
            or outdoor_humidity is None
        ):
            return False

        def calc(temp: float, humidity: float, pollen: int) -> tuple[bool, float, float]:
            dew_point = compute_dew_point(temp, humidity, self._temp_unit)
            simmer_index = compute_simmer_index(temp, humidity, self._temp_unit)
            is_comfortable = (
                humidity <= self._humidity_max
                and self._simmer_index_min <= simmer_index <= self._simmer_index_max
                and dew_point <= self._dew_point_max
                and pollen <= self._pollen_max
            )
            return is_comfortable, dew_point, simmer_index

        realtime: WeatherData | None = self._inputs[Input.REALTIME]

        pollen = (realtime.pollen if realtime else None) or 0

        _, in_dewp, in_si = calc(indoor_temperature, indoor_humidity, 0)
        out_comfort, out_dewp, out_si = calc(outdoor_temperature, outdoor_humidity, pollen)

        self._extra_attributes = {
            Attrib.INDOOR_DEW_POINT: in_dewp,
            Attrib.INDOOR_SIMMER_INDEX: in_si,
            Attrib.OUTDOOR_DEW_POINT: out_dewp,
            Attrib.OUTDOOR_SIMMER_INDEX: out_si,
        }

        self._state[State.CAN_OPEN_WINDOWS] = out_comfort

        forecast: Sequence[WeatherData] | None = self._inputs[Input.FORECAST]

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

            self._state[State.LOW_SIMMER_INDEX] = low_si
            self._state[State.HIGH_SIMMER_INDEX] = high_si
            self._state[State.NEXT_CHANGE_TIME] = next_change_time

        # TODO: create blueprint that uses `next_change_time` if windows can be open "all night"?
        # TODO: blueprint checks `high_simmer_index` if it will be cool tomorrow and conserve heat
        # TODO: need to check when `si_list` will be higher than `in_si`
        # TODO: create `comfort score` and create sensor for that?
        # TODO: allow 'open' if inside SSI above ??? and outside SSI below simmer_index_min
        # TODO: check if temperature forecast is rising or falling currently

        return True
