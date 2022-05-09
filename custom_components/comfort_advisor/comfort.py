"""TODO."""

from datetime import datetime, timedelta
import logging
from typing import Any, Mapping, Sequence

from homeassistant.backports.enum import StrEnum
from homeassistant.const import CONF_TEMPERATURE_UNIT
from homeassistant.util.dt import utcnow
from homeassistant.util.temperature import convert as convert_temp

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
    LOW_SIMMER_INDEX = "low_simmer_index"
    HIGH_SIMMER_INDEX = "high_simmer_index"
    NEXT_CHANGE = "next_change"


ATTR_INDOOR_DEW_POINT = "indoor_dew_point"
ATTR_INDOOR_SIMMER_INDEX = "indoor_simmer_index"
ATTR_OUTDOOR_DEW_POINT = "outdoor_dew_point"
ATTR_OUTDOOR_SIMMER_INDEX = "outdoor_simmer_index"
ATTR_POLLEN = "pollen"


class ComfortCalculator:
    """Calculate comfort states."""

    def __init__(self, hass_temp_unit: str, config: Mapping[str, Any]) -> None:
        """Initialize."""

        # The temperature unit is stored with configuration just in case the unit
        # system is changed later. Convert units to the current unit system.
        config_temp_unit = config[CONF_TEMPERATURE_UNIT]
        self._dew_point_max = convert_temp(
            config[CONF_DEW_POINT_MAX], config_temp_unit, hass_temp_unit
        )
        self._simmer_index_min = convert_temp(
            config[CONF_SIMMER_INDEX_MIN], config_temp_unit, hass_temp_unit
        )
        self._simmer_index_max = convert_temp(
            config[CONF_SIMMER_INDEX_MAX], config_temp_unit, hass_temp_unit
        )
        self._humidity_max = config[CONF_HUMIDITY_MAX]
        self._pollen_max = config[CONF_POLLEN_MAX]
        self._temp_unit = hass_temp_unit

        # state
        self._inputs: dict[str, Any] = {str(x): None for x in Input}  # type: ignore
        self._state: dict[str, Any] = {str(x): None for x in State}  # type: ignore
        self._extra_attributes: dict[str, Any] = {}

    @property
    def extra_attributes(self) -> Mapping[str, Any]:
        """Return extra attributes."""
        return self._extra_attributes

    def update_input(self, key: str, value: Any) -> bool:
        """Update an input value."""
        _LOGGER.debug("update_input called with %s=%s", key, str(value))
        if self._inputs[key] == value:
            return False
        self._inputs[key] = value
        return self.refresh_state()

    def get_state(self, name: str, default: Any = None) -> Any:
        """Retrieve a calculated state."""
        return self._state.get(name, default)

    def refresh_state(self) -> bool:
        """Refresh the calculated state."""
        _LOGGER.debug("_calculate_state called")

        realtime: WeatherData = self._inputs[Input.REALTIME]
        forecast: Sequence[WeatherData] = self._inputs[Input.FORECAST]
        indoor_temperature: float = self._inputs[Input.INDOOR_TEMPERATURE]
        indoor_humidity: float = self._inputs[Input.INDOOR_HUMIDITY]
        outdoor_temperature: float = self._inputs[Input.OUTDOOR_TEMPERATURE]
        outdoor_humidity: float = self._inputs[Input.OUTDOOR_HUMIDITY]

        if (
            # NWS realtime data is unreliable, so continue without it
            forecast is None
            or indoor_temperature is None
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

        pollen = realtime.pollen or 0 if realtime else 0

        _, in_dewp, in_si = calc(indoor_temperature, indoor_humidity, 0)
        out_comfort, out_dewp, out_si = calc(outdoor_temperature, outdoor_humidity, pollen)

        start_time = utcnow()
        end_time = start_time + timedelta(days=1)

        next_change: datetime | None = None
        next_24_hour_si = []

        for interval in filter(lambda x: x.date_time >= start_time, forecast):
            comfort, _, si = calc(interval.temp, interval.humidity, interval.pollen or 0)
            if next_change is None and comfort != out_comfort:
                next_change = interval.date_time
            if interval.date_time <= end_time:
                next_24_hour_si.append(si)

        low_si = min(next_24_hour_si)
        high_si = max(next_24_hour_si)

        self._state[State.CAN_OPEN_WINDOWS] = out_comfort
        self._state[State.LOW_SIMMER_INDEX] = low_si
        self._state[State.HIGH_SIMMER_INDEX] = high_si
        self._state[State.NEXT_CHANGE] = next_change

        self._extra_attributes = {
            ATTR_INDOOR_DEW_POINT: in_dewp,
            ATTR_INDOOR_SIMMER_INDEX: in_si,
            ATTR_OUTDOOR_DEW_POINT: out_dewp,
            ATTR_OUTDOOR_SIMMER_INDEX: out_si,
        }

        if realtime and realtime.pollen is not None:
            self._extra_attributes[ATTR_POLLEN] = realtime.pollen

        return True

        # TODO: create blueprint that uses `next_change_time` if windows can be open "all night"?
        # TODO: blueprint checks `high_simmer_index` if it will be cool tomorrow and conserve heat
        # TODO: need to check when `si_list` will be higher than `in_si`
        # TODO: create `comfort score` and create sensor for that?
        # TODO: allow 'open' if inside SSI above ??? and outside SSI below simmer_index_min
        # TODO: check if temperature forecast is rising or falling currently
