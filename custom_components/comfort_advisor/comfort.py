"""Comfort calculation: decides when windows can be open."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from itertools import dropwhile
import json
import math
from typing import Any, Final

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
from homeassistant.util.unit_conversion import TemperatureDeltaConverter as TDC
from homeassistant.util.unit_system import UnitSystem

from .const import (
    _LOGGER,
    CONF_COOLING_TEMPERATURE_MIN,
    CONF_DEW_POINT_MAX,
    CONF_HUMIDITY_HYSTERESIS,
    CONF_HUMIDITY_MAX,
    CONF_HYSTERESIS,
    CONF_POLLEN_MAX,
    CONF_SIMMER_INDEX_MAX,
    CONF_SIMMER_INDEX_MIN,
    CONF_TEMPERATURE_TOLERANCE,
    DEFAULT_COOLING_TEMPERATURE_MIN,
    DEFAULT_HUMIDITY_HYSTERESIS,
    DEFAULT_HYSTERESIS,
    DEFAULT_TEMPERATURE_TOLERANCE,
    FORECAST_CORRECTION_HOURS,
    FORECAST_CORRECTION_MAX,
    OUTPUT_PRECISION,
    REMAINING_TIME_STEP,
)
from .formulas import (
    calc_dew_point,
    calc_moist_air_enthalpy,
    calc_relative_humidity,
    calc_simmer_index,
)

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
    OPEN_TIME_REMAINING = "open_time_remaining"
    LOW_SIMMER_INDEX = "low_simmer_index"
    HIGH_SIMMER_INDEX = "high_simmer_index"
    LOW_ENTHALPY = "low_enthalpy"
    HIGH_ENTHALPY = "high_enthalpy"
    FORECAST_TEMPERATURE_OFFSET = "forecast_temperature_offset"
    FORECAST_DEW_POINT_OFFSET = "forecast_dew_point_offset"


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


@dataclass(frozen=True, slots=True)
class Margins:
    """How far limits are widened while windows are open (hysteresis)."""

    temperature: float = 0.0
    enthalpy: float = 0.0
    humidity: float = 0.0


NO_MARGINS: Final = Margins()


@dataclass(frozen=True, slots=True)
class ForecastOffsets:
    """Outdoor sensor minus forecast at the current time."""

    temperature: float = 0.0
    dew_point: float = 0.0


NO_OFFSETS: Final = ForecastOffsets()


@dataclass(frozen=True, slots=True)
class ComfortForecast:
    """A forecast hour with the derived comfort values."""

    time: datetime
    temperature: float
    dew_point: float
    simmer_index: float
    enthalpy: float
    comfortable: bool
    advice: Advice


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

        # Temperature differences, as (in the current unit, as enthalpy [kJ/kg]).
        def interval(key: str, default_fahrenheit: float) -> tuple[float, float]:
            value, unit = (
                (config[key], config_temp_unit)
                if key in config
                else (default_fahrenheit, UnitOfTemperature.FAHRENHEIT)
            )
            return (
                TDC.convert(value, unit, temp_unit),
                DRY_AIR_SPECIFIC_HEAT * TDC.convert(value, unit, UnitOfTemperature.CELSIUS),
            )

        self._temp_tolerance, self._enthalpy_tolerance = interval(
            CONF_TEMPERATURE_TOLERANCE, DEFAULT_TEMPERATURE_TOLERANCE
        )
        temp_margin, enthalpy_margin = interval(CONF_HYSTERESIS, DEFAULT_HYSTERESIS)
        self._open_margins = Margins(
            temperature=temp_margin,
            enthalpy=enthalpy_margin,
            humidity=config.get(CONF_HUMIDITY_HYSTERESIS, DEFAULT_HUMIDITY_HYSTERESIS),
        )

        self._offset_max = TDC.convert(
            FORECAST_CORRECTION_MAX, UnitOfTemperature.FAHRENHEIT, temp_unit
        )

        # state
        self._have_changes = False
        self._expires_at: datetime | None = None
        self._input: dict[str, Any] = {str(x): None for x in Input}
        self._calculated: dict[str, Any] = {str(x): None for x in Calculated}
        self._extra_attributes: dict[str, Any] = {}

    @property
    def extra_attributes(self) -> Mapping[str, Any]:
        """Return extra attributes for the "can open windows" sensor."""
        return self._extra_attributes

    @property
    def expires_at(self) -> datetime | None:
        """When the results go stale: the first forecast hour, or None."""
        return self._expires_at

    @property
    def available(self) -> bool:
        """Whether outputs have been calculated from a full set of inputs."""
        return self._calculated[Calculated.CAN_OPEN_WINDOWS] is not None

    def update_input(self, key: str, value: Any) -> None:
        """Update an input value; None means the input is unavailable."""
        _LOGGER.debug("update_input called with %s=%s", key, str(value))
        if self._input[key] != value:
            self._input[key] = value
            self._have_changes = True

    def get_calculated(self, name: str, default: Any = None) -> Any:
        """Retrieve a calculated state."""
        return self._calculated.get(name, default)

    def refresh_state(self) -> bool:
        """Refresh the calculated state; return True if it changed.

        Recalculates when an input changed or when the next forecast hour
        arrives (so change times never fall into the past). Outputs are cleared
        while any input is unavailable.
        """
        expired = self._expires_at is not None and utcnow() >= self._expires_at
        if not self._have_changes and not expired:
            return False
        self._have_changes = False

        if any(value is None for value in self._input.values()):
            return self._clear()

        in_temp: float = self._input[Input.INDOOR_TEMPERATURE]
        in_humidity: float = self._input[Input.INDOOR_HUMIDITY]
        indoor = Indoor(
            temperature=in_temp,
            simmer_index=calc_simmer_index(in_temp, in_humidity, self._temp_unit),
            enthalpy=self._enthalpy(in_temp, in_humidity),
        )

        out_temp: float = self._input[Input.OUTDOOR_TEMPERATURE]
        out_humidity: float = self._input[Input.OUTDOOR_HUMIDITY]
        out_dewp = calc_dew_point(out_temp, out_humidity, self._temp_unit)
        out_ssi = calc_simmer_index(out_temp, out_humidity, self._temp_unit)
        out_enthalpy = self._enthalpy(out_temp, out_humidity)

        # Hysteresis: once windows are open, limits are widened by the margins.
        was_open = self._calculated[Calculated.CAN_OPEN_WINDOWS] is True
        advice_now = self.advise(
            out_temp, out_humidity, out_dewp, out_ssi, out_enthalpy, 0, indoor, is_open=was_open
        )
        open_now = advice_now.can_open

        # Future indoor conditions aren't known, so forecast hours are compared
        # against the current indoor conditions. Near-term hours are corrected by
        # how far the outdoor sensor is from the forecast right now.
        offsets = self.forecast_offsets(self._input[Input.FORECAST], out_temp, out_dewp)
        forecast = self.make_comfort_forecast(
            self._input[Input.FORECAST], indoor, open_now, offsets
        )
        if not forecast:
            return self._clear()

        temp_arr = [entry.temperature for entry in forecast]
        avg_temp = sum(temp_arr) / len(temp_arr)

        ssi_arr = [entry.simmer_index for entry in forecast]
        low_simmer_index = min(ssi_arr)
        high_simmer_index = max(ssi_arr)

        enthalpy_arr = [entry.enthalpy for entry in forecast]
        low_enthalpy = min(enthalpy_arr)
        high_enthalpy = max(enthalpy_arr)

        first_time: datetime | None = None
        second_time: datetime | None = None

        if change := list(dropwhile(lambda x: x.advice.can_open == open_now, forecast)):
            first_time = change[0].time

            if change := list(dropwhile(lambda x: x.advice.can_open != open_now, change)):
                second_time = change[0].time

        # Published values are rounded so tiny input changes don't record new
        # states. Decisions above use the unrounded values.
        self._calculated[Calculated.AVERAGE_TEMPERATURE] = round(avg_temp, OUTPUT_PRECISION)
        self._calculated[Calculated.ENTHALPY] = round(out_enthalpy, OUTPUT_PRECISION)
        self._calculated[Calculated.SIMMER_INDEX] = round(out_ssi, OUTPUT_PRECISION)
        self._calculated[Calculated.CAN_OPEN_WINDOWS] = open_now
        self._calculated[Calculated.LOW_SIMMER_INDEX] = round(low_simmer_index, OUTPUT_PRECISION)
        self._calculated[Calculated.HIGH_SIMMER_INDEX] = round(high_simmer_index, OUTPUT_PRECISION)
        self._calculated[Calculated.LOW_ENTHALPY] = round(low_enthalpy, OUTPUT_PRECISION)
        self._calculated[Calculated.HIGH_ENTHALPY] = round(high_enthalpy, OUTPUT_PRECISION)
        self._calculated[Calculated.FORECAST_TEMPERATURE_OFFSET] = round(
            offsets.temperature, OUTPUT_PRECISION
        )
        self._calculated[Calculated.FORECAST_DEW_POINT_OFFSET] = round(
            offsets.dew_point, OUTPUT_PRECISION
        )
        self._calculated[Calculated.OPEN_WINDOWS_AT] = second_time if open_now else first_time
        self._calculated[Calculated.CLOSE_WINDOWS_AT] = first_time if open_now else second_time
        self._calculated[Calculated.OPEN_TIME_REMAINING] = self._open_time_remaining(
            open_now, first_time if open_now else None
        )
        self._extra_attributes = {ATTR_REASON: advice_now}
        self._expires_at = forecast[0].time

        return True

        # TODO: create blueprint that uses `next_change_time` if windows can be open "all night"?
        # TODO: blueprint checks `high_simmer_index` if it will be cool tomorrow and conserve heat
        # TODO: create `comfort score` and create sensor for that?
        # TODO: check if temperature forecast is rising or falling currently

    def forecast_offsets(
        self, forecast: list[Forecast], out_temp: float, out_dew_point: float
    ) -> ForecastOffsets:
        """Return the outdoor sensor minus the forecast at the current time.

        The forecast is interpolated between the hours before and after now, or
        taken from the nearest hour within an hour. Each offset is limited to
        FORECAST_CORRECTION_MAX. No usable forecast hour means no correction.
        """
        now = utcnow()
        before: tuple[datetime, float, float] | None = None
        after: tuple[datetime, float, float] | None = None
        for entry in forecast:
            if (parsed := self._parse_forecast_entry(entry)) is None:
                continue
            dt, temp, humidity, dew_point = parsed
            if dt <= now:
                before = (dt, temp, dew_point)
            else:
                after = (dt, temp, dew_point)
                break

        if before and after:
            fraction = (now - before[0]) / (after[0] - before[0])
            forecast_temp = before[1] + (after[1] - before[1]) * fraction
            forecast_dew_point = before[2] + (after[2] - before[2]) * fraction
        elif (nearest := before or after) and abs(nearest[0] - now) <= timedelta(hours=1):
            _, forecast_temp, forecast_dew_point = nearest
        else:
            return NO_OFFSETS

        def limit(value: float) -> float:
            return max(-self._offset_max, min(self._offset_max, value))

        return ForecastOffsets(
            temperature=limit(out_temp - forecast_temp),
            dew_point=limit(out_dew_point - forecast_dew_point),
        )

    def make_comfort_forecast(
        self,
        forecast: list[Forecast],
        indoor: Indoor,
        is_open: bool = False,
        offsets: ForecastOffsets = NO_OFFSETS,
    ) -> list[ComfortForecast]:
        """Convert the next 24 hours of the weather forecast into comfort entries.

        Each hour is advised with the windows state carried from the hour before
        (starting with `is_open`), so change times follow the hysteresis.

        `offsets` are added to each hour's temperature and dew point, fading out
        linearly over FORECAST_CORRECTION_HOURS; humidity is recalculated from
        the corrected values.
        """
        fade = timedelta(hours=FORECAST_CORRECTION_HOURS)
        start_time = utcnow()
        end_time = start_time + timedelta(hours=24)
        new_forecast: list[ComfortForecast] = []

        for entry in forecast:
            dt = datetime.fromisoformat(entry[ATTR_FORECAST_TIME])
            if dt <= start_time:  # the current hour comes from the sensors
                continue
            if dt > end_time:
                break

            temp = entry.get(ATTR_FORECAST_TEMP)
            humidity = entry.get(ATTR_FORECAST_HUMIDITY)

            if temp is None or humidity is None:
                _LOGGER.warning("Received invalid forecast entry: %s", json.dumps(entry))
                return new_forecast

            dew_point = entry.get(ATTR_FORECAST_DEW_POINT)
            if dew_point is None:
                dew_point = calc_dew_point(temp, humidity, self._temp_unit)

            if offsets != NO_OFFSETS and (weight := 1 - (dt - start_time) / fade) > 0:
                temp += offsets.temperature * weight
                dew_point = min(dew_point + offsets.dew_point * weight, temp)
                humidity = min(calc_relative_humidity(temp, dew_point, self._temp_unit), 100)

            ssi = calc_simmer_index(temp, humidity, self._temp_unit)
            enthalpy = self._enthalpy(temp, humidity)

            advice = self.advise(
                temp, humidity, dew_point, ssi, enthalpy, 0, indoor, is_open=is_open
            )
            is_open = advice.can_open
            new_forecast.append(
                ComfortForecast(
                    time=dt,
                    temperature=temp,
                    dew_point=dew_point,
                    simmer_index=ssi,
                    enthalpy=enthalpy,
                    comfortable=self.is_comfortable(humidity, dew_point, ssi, 0),
                    advice=advice,
                )
            )

        return new_forecast

    def is_comfortable(
        self,
        humidity: float,
        dew_point: float,
        simmer_index: float,
        pollen: int,
        margins: Margins = NO_MARGINS,
    ) -> bool:
        """Return True if all values are within the comfort limits (widened by `margins`)."""
        return (
            self._simmer_index_min - margins.temperature
            <= simmer_index
            <= self._simmer_index_max + margins.temperature
            and self._is_breathable(humidity, dew_point, pollen, margins)
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
        *,
        is_open: bool = False,
    ) -> Advice:
        """Decide whether outdoor air should be let in.

        Comfortable outdoor air is let in for fresh air unless it would make the
        heating or cooling work harder. Cooler, drier air is also let in to cool
        a warm house, even when it's below the comfortable range.

        While windows are open (`is_open`), every limit that would close them is
        widened by the hysteresis margins, so they only close once a reading is
        past a limit by the margin.
        """
        m = self._open_margins if is_open else NO_MARGINS
        house_is_warm = indoor.simmer_index > self._simmer_index_target
        house_is_cool = indoor.simmer_index < self._simmer_index_target

        if self.is_comfortable(humidity, dew_point, simmer_index, pollen, m):
            if house_is_warm and enthalpy > indoor.enthalpy + self._enthalpy_tolerance + m.enthalpy:
                return Advice.ADDS_HEAT
            if house_is_cool and temp < indoor.temperature - self._temp_tolerance - m.temperature:
                return Advice.ADDS_CHILL
            return Advice.FRESH_AIR

        if (
            indoor.simmer_index > self._simmer_index_target - m.temperature
            and enthalpy < indoor.enthalpy + m.enthalpy
            and temp < indoor.temperature + m.temperature
            and temp >= self._cooling_temp_min - m.temperature
            and self._is_breathable(humidity, dew_point, pollen, m)
        ):
            return Advice.FREE_COOLING

        return Advice.UNCOMFORTABLE

    def _parse_forecast_entry(self, entry: Forecast) -> tuple[datetime, float, float, float] | None:
        """Return (time, temperature, humidity, dew point), or None if incomplete."""
        temp = entry.get(ATTR_FORECAST_TEMP)
        humidity = entry.get(ATTR_FORECAST_HUMIDITY)
        if temp is None or humidity is None:
            return None
        dew_point = entry.get(ATTR_FORECAST_DEW_POINT)
        if dew_point is None:
            dew_point = calc_dew_point(temp, humidity, self._temp_unit)
        return datetime.fromisoformat(entry[ATTR_FORECAST_TIME]), temp, humidity, dew_point

    @staticmethod
    def _open_time_remaining(open_now: bool, close_at: datetime | None) -> float | None:
        """Hours until windows should be closed, rounded to REMAINING_TIME_STEP.

        0 when windows can't be open; None (unknown) when they can stay open
        beyond the forecast.
        """
        if not open_now:
            return 0.0
        if close_at is None:
            return None
        hours = max((close_at - utcnow()).total_seconds() / 3600, 0)
        # Round halves up (round() would round 2.5 steps to 2).
        return math.floor(hours / REMAINING_TIME_STEP + 0.5) * REMAINING_TIME_STEP

    def _clear(self) -> bool:
        """Clear all outputs; return True if they had values."""
        self._expires_at = None
        if not self.available:
            return False
        self._calculated = {str(x): None for x in Calculated}
        self._extra_attributes = {}
        return True

    def _is_breathable(
        self, humidity: float, dew_point: float, pollen: int, margins: Margins = NO_MARGINS
    ) -> bool:
        return (
            dew_point <= self._dew_point_max + margins.temperature
            and humidity <= self._humidity_max + margins.humidity
            and pollen <= self._pollen_max
        )

    def _enthalpy(self, temp: float, humidity: float) -> float:
        return calc_moist_air_enthalpy(
            temp, humidity, STANDARD_PRESSURE_PA, self._temp_unit, UnitOfPressure.PA
        )
