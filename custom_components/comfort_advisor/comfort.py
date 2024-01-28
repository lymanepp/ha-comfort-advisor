"""TODO."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import dropwhile
import json
from typing import Any, Final, Mapping, Required, TypedDict, cast

from homeassistant.backports.enum import StrEnum
from homeassistant.components.weather import (
    ATTR_FORECAST_DEW_POINT,
    ATTR_FORECAST_HUMIDITY,
    ATTR_FORECAST_TEMP,
    ATTR_FORECAST_TIME,
    Forecast,
)
from homeassistant.const import CONF_TEMPERATURE_UNIT, UnitOfPressure
from homeassistant.util.dt import utcnow
from homeassistant.util.unit_conversion import TemperatureConverter as TC
from homeassistant.util.unit_system import UnitSystem

from .const import (
    _LOGGER,
    CONF_DEW_POINT_MAX,
    CONF_HUMIDITY_MAX,
    CONF_POLLEN_MAX,
    CONF_SIMMER_INDEX_MAX,
    CONF_SIMMER_INDEX_MIN,
    CONF_WEATHER,
)
from .formulas import calc_dew_point, calc_moist_air_enthalpy, calc_simmer_index

STANDARD_PRESSURE_PA: Final = 101_325


class Input(StrEnum):  # type: ignore
    """ComfortCalculator inputs."""

    # REALTIME = "realtime"
    FORECAST = "forecast"
    INDOOR_TEMPERATURE = "indoor_temperature"
    INDOOR_HUMIDITY = "indoor_humidity"
    OUTDOOR_TEMPERATURE = "outdoor_temperature"
    OUTDOOR_HUMIDITY = "outdoor_humidity"


class Calculated(StrEnum):  # type: ignore
    """ComfortCalculator outputs."""

    AVERAGE_TEMPERATURE = "average_temperature"
    ENTHALPY = "enthalpy"
    SIMMER_INDEX = "simmer_index"
    CAN_OPEN_WINDOWS = "can_open_windows"
    OPEN_WINDOWS_AT = "open_windows_at"
    CLOSE_WINDOWS_AT = "close_windows_at"
    LOW_SIMMER_INDEX = "low_simmer_index"
    HIGH_SIMMER_INDEX = "high_simmer_index"
    LOW_ENTHALPY = "low_enthalpy"
    HIGH_ENTHALPY = "high_enthalpy"


@dataclass
class ComfortForecast(TypedDict, total=False):
    """Data format returned by weather provider."""

    datetime: Required[datetime]
    temperature: Required[float]
    dew_point: Required[float]
    ssi: Required[float]
    enthalpy: Required[float]
    comfortable: Required[bool]


ATTR_FORECAST_SSI = "ssi"
ATTR_FORECAST_ENTHALPY = "enthalpy"
ATTR_FORECAST_COMFORTABLE = "comfortable"


# ATTR_INDOOR_DEW_POINT = "indoor_dew_point"
# ATTR_INDOOR_SIMMER_INDEX = "indoor_simmer_index"
# ATTR_OUTDOOR_DEW_POINT = "outdoor_dew_point"
# ATTR_OUTDOOR_SIMMER_INDEX = "outdoor_simmer_index"
# ATTR_POLLEN = "pollen"


class ComfortCalculator:
    """Calculate comfort states."""

    def __init__(self, unit_system: UnitSystem, config: Mapping[str, Any]) -> None:
        """Initialize."""

        self._humidity_max: float = config[CONF_HUMIDITY_MAX]
        self._pollen_max: int = config[CONF_POLLEN_MAX]
        self._temp_unit = unit_system.temperature_unit
        self._weather = config[CONF_WEATHER]
        self._dew_point_max = config[CONF_DEW_POINT_MAX]
        self._simmer_index_min = config[CONF_SIMMER_INDEX_MIN]
        self._simmer_index_max = config[CONF_SIMMER_INDEX_MAX]

        # The temperature unit is stored with configuration just in case the unit
        # system is changed later. Convert units to the current unit system.
        if (config_temp_unit := config[CONF_TEMPERATURE_UNIT]) != unit_system.temperature_unit:
            self._dew_point_max = TC.convert(
                self._dew_point_max, config_temp_unit, unit_system.temperature_unit
            )
            self._simmer_index_min = TC.convert(
                self._simmer_index_min, config_temp_unit, unit_system.temperature_unit
            )
            self._simmer_index_max = TC.convert(
                self._simmer_index_max, config_temp_unit, unit_system.temperature_unit
            )

        # state
        self._have_changes = False
        self._input: dict[str, Any] = {str(x): None for x in Input}  # type: ignore
        self._calculated: dict[str, Any] = {str(x): None for x in Calculated}  # type: ignore
        self._extra_attributes: dict[str, Any] = {}

    @property
    def extra_attributes(self) -> Mapping[str, Any]:
        """Return extra attributes."""
        return self._extra_attributes

    def update_input(self, key: str, value: Any) -> None:
        """Update an input value."""
        _LOGGER.debug("update_input called with %s=%s", key, str(value))
        if value is not None and self._input[key] != value:
            self._input[key] = value
            self._have_changes = True

    def get_calculated(self, name: str, default: Any = None) -> Any:
        """Retrieve a calculated state."""
        return self._calculated.get(name, default)

    def refresh_state(self) -> bool:
        """Refresh the calculated state."""
        if not self._have_changes:
            return False
        self._have_changes = False

        if any(value is None for value in self._input.values()):
            return False

        forecast = self.make_comfort_forecast(self._input[Input.FORECAST])
        if not forecast:
            return False

        # realtime: WeatherData = self._inputs[Input.REALTIME]
        # in_temp: float = self._input[Input.INDOOR_TEMPERATURE]
        # in_humidity: float = self._input[Input.INDOOR_HUMIDITY]
        out_temp: float = self._input[Input.OUTDOOR_TEMPERATURE]
        out_humidity: float = self._input[Input.OUTDOOR_HUMIDITY]

        # in_dewp = compute_dew_point(in_temp, in_humidity, self._temp_unit)
        # in_ssi = compute_simmer_index(in_temp, in_humidity, self._temp_unit)
        # in_enthalpy = calc_moist_air_enthalpy(in_temp, in_humidity, self._temp_unit)
        out_dewp = calc_dew_point(out_temp, out_humidity, self._temp_unit)
        out_ssi = calc_simmer_index(out_temp, out_humidity, self._temp_unit)
        out_enthalpy = calc_moist_air_enthalpy(
            out_temp, out_humidity, 101_325, self._temp_unit, UnitOfPressure.PA
        )

        temp_arr = [entry[ATTR_FORECAST_TEMP] for entry in forecast]
        avg_temp = sum(temp_arr) / len(temp_arr)

        ssi_arr = [entry[ATTR_FORECAST_SSI] for entry in forecast]
        low_simmer_index = min(ssi_arr)
        high_simmer_index = max(ssi_arr)

        enthalpy_arr = [entry[ATTR_FORECAST_ENTHALPY] for entry in forecast]
        low_enthalpy = min(enthalpy_arr)
        high_enthalpy = max(enthalpy_arr)

        comfortable_now = self.is_comfortable(out_humidity, out_dewp, out_ssi, 0)

        first_time: datetime | None = None
        second_time: datetime | None = None

        if change := list(
            dropwhile(lambda x: x[ATTR_FORECAST_COMFORTABLE] == comfortable_now, forecast)
        ):
            first_time = change[0][ATTR_FORECAST_TIME]

            if change := list(
                dropwhile(lambda x: x[ATTR_FORECAST_COMFORTABLE] != comfortable_now, change)
            ):
                second_time = change[0][ATTR_FORECAST_TIME]

        self._calculated[Calculated.AVERAGE_TEMPERATURE] = avg_temp
        self._calculated[Calculated.ENTHALPY] = out_enthalpy
        self._calculated[Calculated.SIMMER_INDEX] = out_ssi
        self._calculated[Calculated.CAN_OPEN_WINDOWS] = ["off", "on"][comfortable_now]
        self._calculated[Calculated.LOW_SIMMER_INDEX] = low_simmer_index
        self._calculated[Calculated.HIGH_SIMMER_INDEX] = high_simmer_index
        self._calculated[Calculated.LOW_ENTHALPY] = low_enthalpy
        self._calculated[Calculated.HIGH_ENTHALPY] = high_enthalpy
        self._calculated[Calculated.OPEN_WINDOWS_AT] = (
            second_time if comfortable_now else first_time
        )
        self._calculated[Calculated.CLOSE_WINDOWS_AT] = (
            first_time if comfortable_now else second_time
        )

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
        # TODO: need to check when `ssi_arr` will be higher than `in_ssi`
        # TODO: create `comfort score` and create sensor for that?
        # TODO: check if temperature forecast is rising or falling currently

    def make_comfort_forecast(self, forecast: list[Forecast]) -> list[ComfortForecast]:
        start_time = utcnow()
        end_time = start_time + timedelta(hours=24)
        new_forecast: list[ComfortForecast] = []

        for entry in forecast:
            dt = datetime.fromisoformat(entry[ATTR_FORECAST_TIME])
            if dt < start_time:
                continue
            if dt > end_time:
                break

            temp = cast(float, entry.get(ATTR_FORECAST_TEMP))
            humidity = entry.get(ATTR_FORECAST_HUMIDITY)

            if temp is None or humidity is None:
                _LOGGER.warning("Received invalid forecast entry: %s", json.dumps(entry))
                return new_forecast

            dew_point = entry.get(ATTR_FORECAST_DEW_POINT) or calc_dew_point(
                temp, humidity, self._temp_unit
            )

            ssi = calc_simmer_index(temp, humidity, self._temp_unit)

            enthalpy = calc_moist_air_enthalpy(
                temp, humidity, STANDARD_PRESSURE_PA, self._temp_unit, UnitOfPressure.PA
            )

            comfortable = self.is_comfortable(humidity, dew_point, ssi, 0)

            new_forecast.append(
                {
                    ATTR_FORECAST_TIME: dt,
                    ATTR_FORECAST_TEMP: temp,
                    ATTR_FORECAST_DEW_POINT: dew_point,
                    ATTR_FORECAST_SSI: ssi,
                    ATTR_FORECAST_ENTHALPY: enthalpy,
                    ATTR_FORECAST_COMFORTABLE: comfortable,
                }
            )

        return new_forecast

    def is_comfortable(
        self, humidity: float, dew_point: float, simmer_index: float, pollen: int
    ) -> bool:
        # TODO: use moist air enthalpy instead of dew point and SSI?
        return (
            self._simmer_index_min <= simmer_index <= self._simmer_index_max
            and dew_point <= self._dew_point_max
            and humidity <= self._humidity_max
            and pollen <= self._pollen_max
        )
