"""Tests for the comfort calculation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.const import CONF_TEMPERATURE_UNIT, UnitOfTemperature
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM
import pytest

from custom_components.comfort_advisor import comfort as comfort_module
from custom_components.comfort_advisor.comfort import Calculated, ComfortCalculator, Input
from custom_components.comfort_advisor.const import (
    CONF_DEW_POINT_MAX,
    CONF_HUMIDITY_MAX,
    CONF_POLLEN_MAX,
    CONF_SIMMER_INDEX_MAX,
    CONF_SIMMER_INDEX_MIN,
    CONF_WEATHER,
)
from custom_components.comfort_advisor.formulas import calc_dew_point, calc_simmer_index

NOW = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)

CONFIG_F: dict[str, Any] = {
    CONF_WEATHER: "weather.home",
    CONF_SIMMER_INDEX_MIN: 70.0,
    CONF_SIMMER_INDEX_MAX: 85.0,
    CONF_DEW_POINT_MAX: 60.0,
    CONF_HUMIDITY_MAX: 95.0,
    CONF_POLLEN_MAX: 2,
    CONF_TEMPERATURE_UNIT: UnitOfTemperature.FAHRENHEIT,
}

# (temperature °F, relative humidity %) samples with the default thresholds
NICE = (72.0, 40.0)  # simmer index ~75, dew point ~46, enthalpy ~39.27 kJ/kg
HOT = (90.0, 50.0)  # simmer index ~103
COLD = (60.0, 50.0)  # simmer index ~61
MUGGY = (68.0, 90.0)  # simmer index ~77 but dew point ~65


@pytest.fixture(autouse=True)
def freeze_now(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the calculator's notion of "now"."""
    monkeypatch.setattr(comfort_module, "utcnow", lambda: NOW)


def hourly(*samples: tuple[float, float], start: int = 1) -> list[dict[str, Any]]:
    """Build an hourly forecast beginning `start` hours from NOW."""
    return [
        {
            "datetime": (NOW + timedelta(hours=start + i)).isoformat(),
            "temperature": temp,
            "humidity": humidity,
        }
        for i, (temp, humidity) in enumerate(samples)
    ]


def hour(n: int) -> datetime:
    """Return the time `n` hours from NOW."""
    return NOW + timedelta(hours=n)


def make_calculator(
    forecast: list[dict[str, Any]] | None = None,
    outdoor: tuple[float, float] | None = NICE,
    indoor: tuple[float, float] | None = (75.0, 50.0),
    config: dict[str, Any] | None = None,
    unit_system=US_CUSTOMARY_SYSTEM,
) -> ComfortCalculator:
    """Create a calculator and feed it the given inputs."""
    calc = ComfortCalculator(unit_system, config or CONFIG_F)
    if forecast is not None:
        calc.update_input(Input.FORECAST, forecast)
    if outdoor is not None:
        calc.update_input(Input.OUTDOOR_TEMPERATURE, outdoor[0])
        calc.update_input(Input.OUTDOOR_HUMIDITY, outdoor[1])
    if indoor is not None:
        calc.update_input(Input.INDOOR_TEMPERATURE, indoor[0])
        calc.update_input(Input.INDOOR_HUMIDITY, indoor[1])
    return calc


def comfortable(calc: ComfortCalculator, temp: float, humidity: float) -> bool:
    """Check comfort for a temperature/humidity sample in the calculator's units."""
    unit = calc._temp_unit  # pylint: disable=protected-access
    return calc.is_comfortable(
        humidity,
        calc_dew_point(temp, humidity, unit),
        calc_simmer_index(temp, humidity, unit),
        0,
    )


class TestIsComfortable:
    """Threshold checks."""

    @pytest.mark.parametrize(
        ("sample", "expected"),
        [(NICE, True), (HOT, False), (COLD, False), (MUGGY, False)],
    )
    def test_samples(self, sample, expected):
        """Nice weather is comfortable; hot, cold and muggy weather is not."""
        assert comfortable(make_calculator(), *sample) is expected

    def test_bounds_are_inclusive(self):
        """Values exactly at a threshold count as comfortable."""
        calc = make_calculator()
        assert calc.is_comfortable(95, 60, 70, 2)
        assert calc.is_comfortable(95, 60, 85, 2)

    @pytest.mark.parametrize(
        ("humidity", "dew_point", "simmer_index", "pollen"),
        [
            (95.1, 50, 75, 0),
            (50, 60.1, 75, 0),
            (50, 50, 69.9, 0),
            (50, 50, 85.1, 0),
            (50, 50, 75, 3),
        ],
    )
    def test_each_threshold_is_enforced(self, humidity, dew_point, simmer_index, pollen):
        """Exceeding any single threshold makes it uncomfortable."""
        assert not make_calculator().is_comfortable(humidity, dew_point, simmer_index, pollen)


class TestUnitConversion:
    """Thresholds are stored with their unit and converted to the current unit system."""

    def test_fahrenheit_config_with_metric_system(self):
        """Thresholds saved in °F are converted when the system is metric."""
        calc = make_calculator(unit_system=METRIC_SYSTEM)
        # 72°F / 40% is comfortable; 90°F / 50% is not
        assert comfortable(calc, 22.2, 40)
        assert not comfortable(calc, 32.2, 50)
        # simmer index bounds 70..85°F == 21.1..29.4°C
        assert calc.is_comfortable(50, 10, 21.2, 0)
        assert not calc.is_comfortable(50, 10, 21.0, 0)
        assert calc.is_comfortable(50, 10, 29.4, 0)
        assert not calc.is_comfortable(50, 10, 29.5, 0)
        # dew point max 60°F == 15.6°C
        assert calc.is_comfortable(50, 15.5, 25, 0)
        assert not calc.is_comfortable(50, 15.7, 25, 0)

    def test_matching_units_are_not_converted(self):
        """Thresholds saved in the system's unit are used as-is."""
        config = CONFIG_F | {
            CONF_SIMMER_INDEX_MIN: 21.0,
            CONF_SIMMER_INDEX_MAX: 29.5,
            CONF_DEW_POINT_MAX: 15.5,
            CONF_TEMPERATURE_UNIT: UnitOfTemperature.CELSIUS,
        }
        calc = make_calculator(config=config, unit_system=METRIC_SYSTEM)
        assert calc.is_comfortable(50, 15.5, 21.0, 0)
        assert not calc.is_comfortable(50, 15.6, 21.0, 0)


class TestMakeComfortForecast:
    """Conversion of the weather forecast into comfort entries."""

    def test_skips_past_entries_and_limits_to_24_hours(self):
        """Only entries from now through the next 24 hours are used."""
        forecast = hourly(*[NICE] * 30, start=-3)
        result = make_calculator().make_comfort_forecast(forecast)
        assert result[0]["datetime"] == hour(0)
        assert result[-1]["datetime"] == hour(24)
        assert len(result) == 25

    def test_entry_fields(self):
        """Each entry carries the derived comfort values."""
        (entry,) = make_calculator().make_comfort_forecast(hourly(NICE))
        assert entry["datetime"] == hour(1)
        assert entry["temperature"] == 72.0
        assert entry["dew_point"] == pytest.approx(calc_dew_point(*NICE, "°F"))
        assert entry["ssi"] == pytest.approx(calc_simmer_index(*NICE, "°F"))
        assert entry["enthalpy"] == pytest.approx(39.27, abs=0.01)
        assert entry["comfortable"] is True

    def test_uses_provider_dew_point_when_present(self):
        """A dew point supplied by the weather provider takes precedence."""
        forecast = hourly(NICE)
        forecast[0]["dew_point"] = 65.0  # above the 60°F maximum
        (entry,) = make_calculator().make_comfort_forecast(forecast)
        assert entry["dew_point"] == 65.0
        assert entry["comfortable"] is False

    @pytest.mark.parametrize("missing", ["temperature", "humidity"])
    def test_stops_at_first_incomplete_entry(self, missing):
        """The forecast is truncated at the first entry missing data."""
        forecast = hourly(NICE, NICE, NICE)
        forecast[1][missing] = None
        result = make_calculator().make_comfort_forecast(forecast)
        assert [e["datetime"] for e in result] == [hour(1)]

    def test_empty_forecast(self):
        """An empty forecast produces no entries."""
        assert make_calculator().make_comfort_forecast([]) == []


class TestUpdateInput:
    """Change tracking for inputs."""

    def test_none_is_ignored(self):
        """A None input keeps the previous value."""
        calc = make_calculator(hourly(NICE))
        assert calc.refresh_state()
        calc.update_input(Input.OUTDOOR_TEMPERATURE, None)
        assert not calc.refresh_state()
        assert calc.get_calculated(Calculated.CAN_OPEN_WINDOWS) == "on"

    def test_unchanged_value_does_not_trigger_refresh(self):
        """Repeating the same value is not a change."""
        calc = make_calculator(hourly(NICE))
        assert calc.refresh_state()
        calc.update_input(Input.OUTDOOR_TEMPERATURE, NICE[0])
        assert not calc.refresh_state()

    def test_changed_value_triggers_refresh(self):
        """A new value causes a recalculation."""
        calc = make_calculator(hourly(NICE))
        assert calc.refresh_state()
        calc.update_input(Input.OUTDOOR_TEMPERATURE, HOT[0])
        assert calc.refresh_state()
        assert calc.get_calculated(Calculated.CAN_OPEN_WINDOWS) == "off"


class TestRefreshState:
    """End-to-end calculation of the outputs."""

    @pytest.mark.parametrize("missing", ["forecast", "outdoor", "indoor"])
    def test_requires_all_inputs(self, missing):
        """Nothing is calculated until every input has a value."""
        kwargs: dict[str, Any] = {"forecast": hourly(NICE)}
        kwargs[missing] = None
        calc = make_calculator(**kwargs)
        assert not calc.refresh_state()
        assert all(calc.get_calculated(x) is None for x in Calculated)

    def test_requires_usable_forecast(self):
        """Nothing is calculated when no forecast entries are in range."""
        calc = make_calculator(hourly(NICE, start=-2))
        assert not calc.refresh_state()

    def test_summary_values(self):
        """Averages and extremes come from the forecast; current values from sensors."""
        calc = make_calculator(hourly(NICE, HOT, COLD))
        assert calc.refresh_state()

        ssi = [calc_simmer_index(*s, "°F") for s in (NICE, HOT, COLD)]
        assert calc.get_calculated(Calculated.AVERAGE_TEMPERATURE) == pytest.approx(74.0)
        assert calc.get_calculated(Calculated.LOW_SIMMER_INDEX) == pytest.approx(min(ssi))
        assert calc.get_calculated(Calculated.HIGH_SIMMER_INDEX) == pytest.approx(max(ssi))
        assert calc.get_calculated(Calculated.LOW_ENTHALPY) < calc.get_calculated(
            Calculated.HIGH_ENTHALPY
        )
        # current values come from the outdoor sensors, not the forecast
        assert calc.get_calculated(Calculated.SIMMER_INDEX) == pytest.approx(
            calc_simmer_index(*NICE, "°F")
        )
        assert calc.get_calculated(Calculated.ENTHALPY) == pytest.approx(39.27, abs=0.01)

    def test_comfortable_now_then_close_then_reopen(self):
        """Close at the first bad hour, reopen at the next good one."""
        calc = make_calculator(hourly(NICE, NICE, HOT, HOT, HOT, NICE, NICE), outdoor=NICE)
        assert calc.refresh_state()
        assert calc.get_calculated(Calculated.CAN_OPEN_WINDOWS) == "on"
        assert calc.get_calculated(Calculated.CLOSE_WINDOWS_AT) == hour(3)
        assert calc.get_calculated(Calculated.OPEN_WINDOWS_AT) == hour(6)

    def test_uncomfortable_now_then_open_then_close(self):
        """Open at the first good hour, close at the next bad one."""
        calc = make_calculator(hourly(COLD, NICE, NICE, HOT), outdoor=COLD)
        assert calc.refresh_state()
        assert calc.get_calculated(Calculated.CAN_OPEN_WINDOWS) == "off"
        assert calc.get_calculated(Calculated.OPEN_WINDOWS_AT) == hour(2)
        assert calc.get_calculated(Calculated.CLOSE_WINDOWS_AT) == hour(4)

    def test_comfortable_all_day(self):
        """No change times when it stays comfortable."""
        calc = make_calculator(hourly(*[NICE] * 24), outdoor=NICE)
        assert calc.refresh_state()
        assert calc.get_calculated(Calculated.CAN_OPEN_WINDOWS) == "on"
        assert calc.get_calculated(Calculated.CLOSE_WINDOWS_AT) is None
        assert calc.get_calculated(Calculated.OPEN_WINDOWS_AT) is None

    def test_uncomfortable_all_day(self):
        """No change times when it stays uncomfortable."""
        calc = make_calculator(hourly(*[HOT] * 24), outdoor=HOT)
        assert calc.refresh_state()
        assert calc.get_calculated(Calculated.CAN_OPEN_WINDOWS) == "off"
        assert calc.get_calculated(Calculated.OPEN_WINDOWS_AT) is None
        assert calc.get_calculated(Calculated.CLOSE_WINDOWS_AT) is None

    def test_opens_but_does_not_close_within_forecast(self):
        """Close time is unknown if comfort lasts past the forecast."""
        calc = make_calculator(hourly(HOT, HOT, NICE, NICE), outdoor=HOT)
        assert calc.refresh_state()
        assert calc.get_calculated(Calculated.OPEN_WINDOWS_AT) == hour(3)
        assert calc.get_calculated(Calculated.CLOSE_WINDOWS_AT) is None

    def test_current_state_uses_sensors_not_forecast(self):
        """Current state comes from the sensors, not the forecast."""
        # Sensors say it's hot now even though the next forecast hour is nice.
        calc = make_calculator(hourly(NICE, NICE, HOT), outdoor=HOT)
        assert calc.refresh_state()
        assert calc.get_calculated(Calculated.CAN_OPEN_WINDOWS) == "off"
        assert calc.get_calculated(Calculated.OPEN_WINDOWS_AT) == hour(1)
        assert calc.get_calculated(Calculated.CLOSE_WINDOWS_AT) == hour(3)
