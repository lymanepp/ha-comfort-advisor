"""Comfort calculation: decides when windows can be open."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from itertools import dropwhile
import json
from typing import Any, Final, Required, TypedDict, cast

from homeassistant.components.weather import (
    ATTR_FORECAST_DEW_POINT,
    ATTR_FORECAST_HUMIDITY,
    ATTR_FORECAST_TEMP,
    ATTR_FORECAST_TIME,
    Forecast,
)
from homeassistant.const import CONF_TEMPERATURE_UNIT, UnitOfPressure, UnitOfTemperature
from homeassistant.util.dt import utcnow
from homeassistant.util.unit_conversion import TemperatureConverter as TC
from homeassistant.util.unit_system import UnitSystem

from .const import (
    _LOGGER,
    CONF_COOLING_TEMPERATURE_MIN,
    CONF_DEW_POINT_MAX,
    CONF_HUMIDITY_MAX,
    CONF_POLLEN_MAX,
    CONF_SIMMER_INDEX_MAX,
    CONF_SIMMER_INDEX_MIN,
    CONF_TEMPERATURE_TOLERANCE,
    CONF_WEATHER,
    DEFAULT_COOLING_TEMPERATURE_MIN,
    DEFAULT_TEMPERATURE_TOLERANCE,
)
from .formulas import calc_dew_point, calc_moist_air_enthalpy, calc_simmer_index

STANDARD_PRESSURE_PA: Final = 101_325

# Specific heat of dry air [kJ/(kg·K)], used to express the temperature
# tolerance as an equivalent enthalpy tolerance.
DRY_AIR_SPECIFIC_HEAT: Final = 1.006


class Input(StrEnum):
    """ComfortCalculator inputs."""

    FORECAST = "forecast"
    INDOOR_TEMPERATURE = "indoor_temperature"
    INDOOR_HUMIDITY = "indoor_humidity"
    OUTDOOR_TEMPERATURE = "outdoor_temperature"
    OUTDOOR_HUMIDITY = "outdoor_humidity"


class Calculated(StrEnum):
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


class Advice(StrEnum):
    """Why windows should be open or closed."""

    FRESH_AIR = "fresh_air"
    """Open: comfortable outside and it doesn't cost energy."""

    FREE_COOLING = "free_cooling"
    """Open: cooler, drier outdoor air cools a warm house."""

    ADDS_HEAT = "adds_heat"
    """Closed: comfortable outside, but it would add heat/moisture to a warm house."""

    ADDS_CHILL = "adds_chill"
    """Closed: comfortable outside, but it would chill a cool house."""

    UNCOMFORTABLE = "uncomfortable"
    """Closed: uncomfortable outside and no cooling benefit."""

    @property
    def can_open(self) -> bool:
        """Whether this advice means windows can be open."""
        return self in (Advice.FRESH_AIR, Advice.FREE_COOLING)


ATTR_REASON: Final = "reason"


@dataclass(frozen=True, slots=True)
class Indoor:
    """Indoor conditions that outdoor air is compared against."""

    temperature: float
    simmer_index: float
    enthalpy: float


class ComfortForecast(TypedDict, total=False):
    """A forecast hour with the derived comfort values."""

    datetime: Required[datetime]
    temperature: Required[float]
    dew_point: Required[float]
    ssi: Required[float]
    enthalpy: Required[float]
    comfortable: Required[bool]
    advice: Required[Advice]


ATTR_FORECAST_SSI = "ssi"
ATTR_FORECAST_ENTHALPY = "enthalpy"
ATTR_FORECAST_COMFORTABLE = "comfortable"
ATTR_FORECAST_ADVICE = "advice"


class ComfortCalculator:
    """Calculate comfort states."""

    def __init__(self, unit_system: UnitSystem, config: Mapping[str, Any]) -> None:
        """Initialize."""
        temp_unit = unit_system.temperature_unit
        config_temp_unit = config[CONF_TEMPERATURE_UNIT]

        # Temperatures are stored with the unit in use when they were configured,
        # in case the unit system is changed later. Convert to the current unit.
        def temperature(key: str) -> float:
            return TC.convert(config[key], config_temp_unit, temp_unit)

        self._temp_unit = temp_unit
        self._weather = config[CONF_WEATHER]
        self._humidity_max: float = config[CONF_HUMIDITY_MAX]
        self._pollen_max: int = config[CONF_POLLEN_MAX]
        self._dew_point_max = temperature(CONF_DEW_POINT_MAX)
        self._simmer_index_min = temperature(CONF_SIMMER_INDEX_MIN)
        self._simmer_index_max = temperature(CONF_SIMMER_INDEX_MAX)
        self._simmer_index_target = (self._simmer_index_min + self._simmer_index_max) / 2

        # Entries created before these settings existed fall back to defaults (°F).
        if CONF_COOLING_TEMPERATURE_MIN in config:
            self._cooling_temp_min = temperature(CONF_COOLING_TEMPERATURE_MIN)
        else:
            self._cooling_temp_min = TC.convert(
                DEFAULT_COOLING_TEMPERATURE_MIN, UnitOfTemperature.FAHRENHEIT, temp_unit
            )
        if CONF_TEMPERATURE_TOLERANCE in config:
            tolerance, tolerance_unit = config[CONF_TEMPERATURE_TOLERANCE], config_temp_unit
        else:
            tolerance, tolerance_unit = (
                DEFAULT_TEMPERATURE_TOLERANCE,
                UnitOfTemperature.FAHRENHEIT,
            )
        self._temp_tolerance = TC.convert_interval(tolerance, tolerance_unit, temp_unit)
        self._enthalpy_tolerance = DRY_AIR_SPECIFIC_HEAT * TC.convert_interval(
            tolerance, tolerance_unit, UnitOfTemperature.CELSIUS
        )

        # state
        self._have_changes = False
        self._input: dict[str, Any] = {str(x): None for x in Input}
        self._calculated: dict[str, Any] = {str(x): None for x in Calculated}
        self._extra_attributes: dict[str, Any] = {}

    @property
    def extra_attributes(self) -> Mapping[str, Any]:
        """Return extra attributes for the "can open windows" sensor."""
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

        in_temp: float = self._input[Input.INDOOR_TEMPERATURE]
        in_humidity: float = self._input[Input.INDOOR_HUMIDITY]
        indoor = Indoor(
            temperature=in_temp,
            simmer_index=calc_simmer_index(in_temp, in_humidity, self._temp_unit),
            enthalpy=self._enthalpy(in_temp, in_humidity),
        )

        # Future indoor conditions aren't known, so forecast hours are compared
        # against the current indoor conditions.
        forecast = self.make_comfort_forecast(self._input[Input.FORECAST], indoor)
        if not forecast:
            return False

        out_temp: float = self._input[Input.OUTDOOR_TEMPERATURE]
        out_humidity: float = self._input[Input.OUTDOOR_HUMIDITY]
        out_dewp = calc_dew_point(out_temp, out_humidity, self._temp_unit)
        out_ssi = calc_simmer_index(out_temp, out_humidity, self._temp_unit)
        out_enthalpy = self._enthalpy(out_temp, out_humidity)

        temp_arr = [entry[ATTR_FORECAST_TEMP] for entry in forecast]
        avg_temp = sum(temp_arr) / len(temp_arr)

        ssi_arr = [entry[ATTR_FORECAST_SSI] for entry in forecast]
        low_simmer_index = min(ssi_arr)
        high_simmer_index = max(ssi_arr)

        enthalpy_arr = [entry[ATTR_FORECAST_ENTHALPY] for entry in forecast]
        low_enthalpy = min(enthalpy_arr)
        high_enthalpy = max(enthalpy_arr)

        advice_now = self.advise(out_temp, out_humidity, out_dewp, out_ssi, out_enthalpy, 0, indoor)
        open_now = advice_now.can_open

        first_time: datetime | None = None
        second_time: datetime | None = None

        if change := list(
            dropwhile(lambda x: x[ATTR_FORECAST_ADVICE].can_open == open_now, forecast)
        ):
            first_time = change[0][ATTR_FORECAST_TIME]

            if change := list(
                dropwhile(lambda x: x[ATTR_FORECAST_ADVICE].can_open != open_now, change)
            ):
                second_time = change[0][ATTR_FORECAST_TIME]

        self._calculated[Calculated.AVERAGE_TEMPERATURE] = avg_temp
        self._calculated[Calculated.ENTHALPY] = out_enthalpy
        self._calculated[Calculated.SIMMER_INDEX] = out_ssi
        self._calculated[Calculated.CAN_OPEN_WINDOWS] = "on" if open_now else "off"
        self._calculated[Calculated.LOW_SIMMER_INDEX] = low_simmer_index
        self._calculated[Calculated.HIGH_SIMMER_INDEX] = high_simmer_index
        self._calculated[Calculated.LOW_ENTHALPY] = low_enthalpy
        self._calculated[Calculated.HIGH_ENTHALPY] = high_enthalpy
        self._calculated[Calculated.OPEN_WINDOWS_AT] = second_time if open_now else first_time
        self._calculated[Calculated.CLOSE_WINDOWS_AT] = first_time if open_now else second_time
        self._extra_attributes = {ATTR_REASON: advice_now}

        return True

        # TODO: create blueprint that uses `next_change_time` if windows can be open "all night"?
        # TODO: blueprint checks `high_simmer_index` if it will be cool tomorrow and conserve heat
        # TODO: create `comfort score` and create sensor for that?
        # TODO: check if temperature forecast is rising or falling currently

    def make_comfort_forecast(
        self, forecast: list[Forecast], indoor: Indoor
    ) -> list[ComfortForecast]:
        """Convert the next 24 hours of the weather forecast into comfort entries."""
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
            enthalpy = self._enthalpy(temp, humidity)

            new_forecast.append(
                {
                    ATTR_FORECAST_TIME: dt,
                    ATTR_FORECAST_TEMP: temp,
                    ATTR_FORECAST_DEW_POINT: dew_point,
                    ATTR_FORECAST_SSI: ssi,
                    ATTR_FORECAST_ENTHALPY: enthalpy,
                    ATTR_FORECAST_COMFORTABLE: self.is_comfortable(humidity, dew_point, ssi, 0),
                    ATTR_FORECAST_ADVICE: self.advise(
                        temp, humidity, dew_point, ssi, enthalpy, 0, indoor
                    ),
                }
            )

        return new_forecast

    def is_comfortable(
        self, humidity: float, dew_point: float, simmer_index: float, pollen: int
    ) -> bool:
        """Return True if all values are within the configured comfort limits."""
        return (
            self._simmer_index_min <= simmer_index <= self._simmer_index_max
            and self._is_breathable(humidity, dew_point, pollen)
        )

    def advise(  # pylint: disable=too-many-arguments
        self,
        temp: float,
        humidity: float,
        dew_point: float,
        simmer_index: float,
        enthalpy: float,
        pollen: int,
        indoor: Indoor,
    ) -> Advice:
        """Decide whether outdoor air should be let in.

        Comfortable outdoor air is let in for fresh air unless it would make the
        heating or cooling work harder. Cooler, drier air is also let in to cool
        a warm house, even when it's below the comfortable range.
        """
        house_is_warm = indoor.simmer_index > self._simmer_index_target
        house_is_cool = indoor.simmer_index < self._simmer_index_target

        if self.is_comfortable(humidity, dew_point, simmer_index, pollen):
            if house_is_warm and enthalpy > indoor.enthalpy + self._enthalpy_tolerance:
                return Advice.ADDS_HEAT
            if house_is_cool and temp < indoor.temperature - self._temp_tolerance:
                return Advice.ADDS_CHILL
            return Advice.FRESH_AIR

        if (
            house_is_warm
            and enthalpy < indoor.enthalpy
            and temp < indoor.temperature
            and temp >= self._cooling_temp_min
            and self._is_breathable(humidity, dew_point, pollen)
        ):
            return Advice.FREE_COOLING

        return Advice.UNCOMFORTABLE

    def _is_breathable(self, humidity: float, dew_point: float, pollen: int) -> bool:
        return (
            dew_point <= self._dew_point_max
            and humidity <= self._humidity_max
            and pollen <= self._pollen_max
        )

    def _enthalpy(self, temp: float, humidity: float) -> float:
        return calc_moist_air_enthalpy(
            temp, humidity, STANDARD_PRESSURE_PA, self._temp_unit, UnitOfPressure.PA
        )
