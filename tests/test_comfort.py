"""Tests for the comfort calculation."""

from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.const import CONF_TEMPERATURE_UNIT, UnitOfTemperature
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM
import pytest

from custom_components.comfort_advisor import comfort as comfort_module
from custom_components.comfort_advisor.comfort import (
    ATTR_REASON,
    Advice,
    Calculated,
    ComfortCalculator,
    Indoor,
    Input,
)
from custom_components.comfort_advisor.const import (
    CONF_COOLING_TEMPERATURE_MIN,
    CONF_DEW_POINT_MAX,
    CONF_HUMIDITY_HYSTERESIS,
    CONF_HUMIDITY_MAX,
    CONF_HYSTERESIS,
    CONF_POLLEN_MAX,
    CONF_SIMMER_INDEX_MAX,
    CONF_SIMMER_INDEX_MIN,
    CONF_TEMPERATURE_TOLERANCE,
    CONF_WEATHER,
)
from custom_components.comfort_advisor.formulas import (
    calc_dew_point,
    calc_moist_air_enthalpy,
    calc_relative_humidity,
    calc_simmer_index,
)

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
COOL_NIGHT = (64.0, 50.0)  # simmer index ~67, below the comfortable range

# Indoor (temperature °F, relative humidity %) samples. The comfort target is the
# middle of the simmer index range: 77.5.
SLIGHTLY_COOL_HOUSE = (71.0, 40.0)  # simmer index ~75
COOL_HOUSE = (72.0, 40.0)  # simmer index ~77, just below the target
WARM_HOUSE = (80.0, 55.0)  # simmer index ~91
WARM_DRY_HOUSE = (78.0, 30.0)  # simmer index ~82, but little moisture


class Clock:
    """Adjustable stand-in for the calculator's clock."""

    def __init__(self) -> None:
        """Start at NOW."""
        self.now = NOW

    def __call__(self) -> datetime:
        """Return the current time."""
        return self.now


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    """Pin the calculator's notion of "now"; tests can move it forward."""
    clock = Clock()
    monkeypatch.setattr(comfort_module, "utcnow", clock)
    return clock


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


def indoor(temp: float, humidity: float) -> Indoor:
    """Build indoor conditions in °F."""
    return Indoor(
        temperature=temp,
        simmer_index=calc_simmer_index(temp, humidity, "°F"),
        enthalpy=calc_moist_air_enthalpy(temp, humidity, 101_325, "°F", "Pa"),
    )


INDOOR = indoor(*SLIGHTLY_COOL_HOUSE)


def hour(n: int) -> datetime:
    """Return the time `n` hours from NOW."""
    return NOW + timedelta(hours=n)


def make_calculator(
    forecast: list[dict[str, Any]] | None = None,
    outdoor: tuple[float, float] | None = NICE,
    indoor: tuple[float, float] | None = SLIGHTLY_COOL_HOUSE,
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
        """Only entries after now, through the next 24 hours, are used.

        The hour starting now is skipped: current conditions come from the sensors.
        """
        forecast = hourly(*[NICE] * 30, start=-3)
        result = make_calculator().make_comfort_forecast(forecast, INDOOR)
        assert result[0].time == hour(1)
        assert result[-1].time == hour(24)
        assert len(result) == 24

    def test_expiry_moves_past_the_current_hour(self, clock: Clock):
        """When the first forecast hour arrives, the next one becomes the expiry.

        Otherwise a timer set for the expiry would fire again immediately.
        """
        calc = make_calculator(hourly(NICE, NICE, NICE))
        assert calc.refresh_state()
        assert calc.expires_at == hour(1)
        clock.now = hour(1)
        assert calc.refresh_state()
        assert calc.expires_at == hour(2)

    def test_entry_fields(self):
        """Each entry carries the derived comfort values."""
        (entry,) = make_calculator().make_comfort_forecast(hourly(NICE), INDOOR)
        assert entry.time == hour(1)
        assert entry.temperature == 72.0
        assert entry.dew_point == pytest.approx(calc_dew_point(*NICE, "°F"))
        assert entry.simmer_index == pytest.approx(calc_simmer_index(*NICE, "°F"))
        assert entry.enthalpy == pytest.approx(39.27, abs=0.01)
        assert entry.comfortable is True

    def test_uses_provider_dew_point_of_zero(self):
        """A provider dew point of exactly 0 is used, not treated as missing."""
        forecast = hourly(NICE)
        forecast[0]["dew_point"] = 0.0
        (entry,) = make_calculator().make_comfort_forecast(forecast, INDOOR)
        assert entry.dew_point == 0.0

    def test_uses_provider_dew_point_when_present(self):
        """A dew point supplied by the weather provider takes precedence."""
        forecast = hourly(NICE)
        forecast[0]["dew_point"] = 65.0  # above the 60°F maximum
        (entry,) = make_calculator().make_comfort_forecast(forecast, INDOOR)
        assert entry.dew_point == 65.0
        assert entry.comfortable is False

    @pytest.mark.parametrize("missing", ["temperature", "humidity"])
    def test_stops_at_first_incomplete_entry(self, missing):
        """The forecast is truncated at the first entry missing data."""
        forecast = hourly(NICE, NICE, NICE)
        forecast[1][missing] = None
        result = make_calculator().make_comfort_forecast(forecast, INDOOR)
        assert [e.time for e in result] == [hour(1)]

    def test_empty_forecast(self):
        """An empty forecast produces no entries."""
        assert make_calculator().make_comfort_forecast([], INDOOR) == []


class TestUpdateInput:
    """Change tracking for inputs."""

    @pytest.mark.parametrize("key", list(Input))
    def test_unavailable_input_clears_outputs(self, key):
        """When any input becomes unavailable, all outputs are cleared."""
        calc = make_calculator(hourly(NICE))
        assert calc.refresh_state()
        assert calc.available

        calc.update_input(key, None)
        assert calc.refresh_state()
        assert not calc.available
        assert all(calc.get_calculated(x) is None for x in Calculated)
        assert calc.extra_attributes == {}

        # nothing more to clear
        assert not calc.refresh_state()

    def test_outputs_return_with_input(self):
        """Outputs are recalculated when the input comes back."""
        calc = make_calculator(hourly(NICE))
        assert calc.refresh_state()
        calc.update_input(Input.OUTDOOR_TEMPERATURE, None)
        assert calc.refresh_state()
        calc.update_input(Input.OUTDOOR_TEMPERATURE, NICE[0])
        assert calc.refresh_state()
        assert calc.available
        assert calc.get_calculated(Calculated.CAN_OPEN_WINDOWS) is True

    def test_empty_forecast_clears_outputs(self):
        """A forecast with no usable hours clears the outputs."""
        calc = make_calculator(hourly(NICE))
        assert calc.refresh_state()
        calc.update_input(Input.FORECAST, hourly(NICE, start=-3))
        assert calc.refresh_state()
        assert not calc.available

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
        assert calc.get_calculated(Calculated.CAN_OPEN_WINDOWS) is False


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

        # Published values are rounded to 0.1.
        ssi = [calc_simmer_index(*s, "°F") for s in (NICE, HOT, COLD)]
        assert calc.get_calculated(Calculated.AVERAGE_TEMPERATURE) == 74.0
        assert calc.get_calculated(Calculated.LOW_SIMMER_INDEX) == round(min(ssi), 1)
        assert calc.get_calculated(Calculated.HIGH_SIMMER_INDEX) == round(max(ssi), 1)
        assert calc.get_calculated(Calculated.LOW_ENTHALPY) < calc.get_calculated(
            Calculated.HIGH_ENTHALPY
        )
        # current values come from the outdoor sensors, not the forecast
        assert calc.get_calculated(Calculated.SIMMER_INDEX) == round(
            calc_simmer_index(*NICE, "°F"), 1
        )
        assert calc.get_calculated(Calculated.ENTHALPY) == 39.3

    def test_comfortable_now_then_close_then_reopen(self):
        """Close at the first bad hour, reopen at the next good one."""
        calc = make_calculator(hourly(NICE, NICE, HOT, HOT, HOT, NICE, NICE), outdoor=NICE)
        assert calc.refresh_state()
        assert calc.get_calculated(Calculated.CAN_OPEN_WINDOWS) is True
        assert calc.get_calculated(Calculated.CLOSE_WINDOWS_AT) == hour(3)
        assert calc.get_calculated(Calculated.OPEN_WINDOWS_AT) == hour(6)

    def test_uncomfortable_now_then_open_then_close(self):
        """Open at the first good hour, close at the next bad one."""
        calc = make_calculator(hourly(COLD, NICE, NICE, HOT), outdoor=COLD)
        assert calc.refresh_state()
        assert calc.get_calculated(Calculated.CAN_OPEN_WINDOWS) is False
        assert calc.get_calculated(Calculated.OPEN_WINDOWS_AT) == hour(2)
        assert calc.get_calculated(Calculated.CLOSE_WINDOWS_AT) == hour(4)

    def test_comfortable_all_day(self):
        """No change times when it stays comfortable."""
        calc = make_calculator(hourly(*[NICE] * 24), outdoor=NICE)
        assert calc.refresh_state()
        assert calc.get_calculated(Calculated.CAN_OPEN_WINDOWS) is True
        assert calc.get_calculated(Calculated.CLOSE_WINDOWS_AT) is None
        assert calc.get_calculated(Calculated.OPEN_WINDOWS_AT) is None

    def test_uncomfortable_all_day(self):
        """No change times when it stays uncomfortable."""
        calc = make_calculator(hourly(*[HOT] * 24), outdoor=HOT)
        assert calc.refresh_state()
        assert calc.get_calculated(Calculated.CAN_OPEN_WINDOWS) is False
        assert calc.get_calculated(Calculated.OPEN_WINDOWS_AT) is None
        assert calc.get_calculated(Calculated.CLOSE_WINDOWS_AT) is None

    def test_opens_but_does_not_close_within_forecast(self):
        """Close time is unknown if comfort lasts past the forecast."""
        calc = make_calculator(hourly(HOT, HOT, NICE, NICE), outdoor=HOT)
        assert calc.refresh_state()
        assert calc.get_calculated(Calculated.OPEN_WINDOWS_AT) == hour(3)
        assert calc.get_calculated(Calculated.CLOSE_WINDOWS_AT) is None

    def test_current_state_uses_sensors_not_forecast(self):
        """Current state comes from the sensors, not the forecast.

        The forecast starts after the correction window, so it isn't corrected.
        """
        # Sensors say it's hot now even though the next forecast hour is nice.
        calc = make_calculator(hourly(NICE, NICE, HOT, start=4), outdoor=HOT)
        assert calc.refresh_state()
        assert calc.get_calculated(Calculated.CAN_OPEN_WINDOWS) is False
        assert calc.get_calculated(Calculated.OPEN_WINDOWS_AT) == hour(4)
        assert calc.get_calculated(Calculated.CLOSE_WINDOWS_AT) == hour(6)


def advise(
    outdoor: tuple[float, float],
    house: tuple[float, float],
    calc: ComfortCalculator | None = None,
) -> Advice:
    """Advise for °F outdoor and indoor samples."""
    calc = calc or make_calculator()
    temp, humidity = outdoor
    return calc.advise(
        temp,
        humidity,
        calc_dew_point(temp, humidity, "°F"),
        calc_simmer_index(temp, humidity, "°F"),
        calc_moist_air_enthalpy(temp, humidity, 101_325, "°F", "Pa"),
        0,
        indoor(*house),
    )


class TestAdvise:
    """Indoor-aware window advice."""

    def test_fresh_air_when_comfortable_and_house_is_warm(self):
        """Comfortable outdoor air with less heat than the house is let in."""
        assert advise(NICE, WARM_HOUSE) is Advice.FRESH_AIR

    def test_fresh_air_when_comfortable_and_close_to_indoor(self):
        """Comfortable outdoor air near the indoor temperature is let in."""
        assert advise(NICE, COOL_HOUSE) is Advice.FRESH_AIR

    def test_adds_heat(self):
        """Comfortable but more heat/moisture than a warm house is kept out."""
        assert advise((75.0, 55.0), WARM_DRY_HOUSE) is Advice.ADDS_HEAT

    def test_heat_within_tolerance_is_fresh_air(self):
        """Slightly more heat than a warm house is within the tolerance."""
        # 41.59 vs 41.23 kJ/kg; the 2°F tolerance is worth about 1.12 kJ/kg
        assert advise((74.0, 40.0), WARM_DRY_HOUSE) is Advice.FRESH_AIR

    def test_adds_chill(self):
        """Comfortable but colder than a cool house is kept out."""
        assert advise((69.0, 60.0), COOL_HOUSE) is Advice.ADDS_CHILL

    def test_chill_within_tolerance_is_fresh_air(self):
        """Being slightly colder than a cool house is within the tolerance."""
        assert advise((71.2, 45.0), COOL_HOUSE) is Advice.FRESH_AIR

    def test_tolerance_setting(self):
        """A larger tolerance lets in cooler comfortable air."""
        calc = make_calculator(config=CONFIG_F | {CONF_TEMPERATURE_TOLERANCE: 4.0})
        assert advise((69.0, 60.0), COOL_HOUSE, calc) is Advice.FRESH_AIR

    def test_free_cooling(self):
        """Cool night air is let into a warm house even though it's not comfortable."""
        assert advise(COOL_NIGHT, WARM_HOUSE) is Advice.FREE_COOLING

    def test_free_cooling_stops_at_comfort_target(self):
        """Free cooling only applies while the house is warmer than the target."""
        assert advise(COOL_NIGHT, COOL_HOUSE) is Advice.UNCOMFORTABLE

    def test_free_cooling_floor(self):
        """Air colder than the floor is never let in for cooling."""
        assert advise((58.0, 50.0), WARM_HOUSE) is Advice.UNCOMFORTABLE
        calc = make_calculator(config=CONFIG_F | {CONF_COOLING_TEMPERATURE_MIN: 55.0})
        assert advise((58.0, 50.0), WARM_HOUSE, calc) is Advice.FREE_COOLING

    def test_free_cooling_respects_dew_point(self):
        """Humid air isn't let in for cooling."""
        assert advise((66.0, 90.0), WARM_HOUSE) is Advice.UNCOMFORTABLE

    def test_free_cooling_needs_less_heat(self):
        """Cooler but moister air holding more heat than the house isn't let in."""
        # 63°F / 85%: 43.7 kJ/kg vs the house's 41.2, dew point 58°F (allowed)
        assert advise((63.0, 85.0), WARM_DRY_HOUSE) is Advice.UNCOMFORTABLE

    def test_free_cooling_needs_cooler_air(self):
        """Hot, dry air has less enthalpy but would still warm the house."""
        assert advise((86.0, 15.0), WARM_HOUSE) is Advice.UNCOMFORTABLE

    @pytest.mark.parametrize("sample", [HOT, MUGGY])
    def test_uncomfortable(self, sample):
        """Uncomfortable air without a cooling benefit is kept out."""
        assert advise(sample, WARM_HOUSE) is Advice.UNCOMFORTABLE

    @pytest.mark.parametrize(
        ("advice", "expected"),
        [
            (Advice.FRESH_AIR, True),
            (Advice.FREE_COOLING, True),
            (Advice.ADDS_HEAT, False),
            (Advice.ADDS_CHILL, False),
            (Advice.UNCOMFORTABLE, False),
        ],
    )
    def test_can_open(self, advice, expected):
        """Only fresh air and free cooling mean open."""
        assert advice.can_open is expected


class TestAdviceSettings:
    """The new settings are converted and defaulted like the others."""

    def test_defaults_for_older_entries(self):
        """Entries saved before these settings existed use 60°F and 2°F."""
        assert CONF_COOLING_TEMPERATURE_MIN not in CONFIG_F
        calc = make_calculator()
        assert calc._cooling_temp_min == pytest.approx(60.0)  # pylint: disable=protected-access
        assert calc._temp_tolerance == pytest.approx(2.0)  # pylint: disable=protected-access

    def test_defaults_converted_to_metric(self):
        """Defaults are converted to °C on a metric system."""
        calc = make_calculator(unit_system=METRIC_SYSTEM)
        # pylint: disable=protected-access
        assert calc._cooling_temp_min == pytest.approx(15.56, abs=0.01)
        assert calc._temp_tolerance == pytest.approx(1.111, abs=0.001)
        assert calc._enthalpy_tolerance == pytest.approx(1.118, abs=0.001)

    def test_saved_fahrenheit_settings_converted_to_metric(self):
        """The floor converts as a temperature, the tolerance as a difference."""
        config = CONFIG_F | {
            CONF_COOLING_TEMPERATURE_MIN: 50.0,
            CONF_TEMPERATURE_TOLERANCE: 9.0,
        }
        calc = make_calculator(config=config, unit_system=METRIC_SYSTEM)
        # pylint: disable=protected-access
        assert calc._cooling_temp_min == pytest.approx(10.0)
        assert calc._temp_tolerance == pytest.approx(5.0)


class TestIndoorAwareRefresh:
    """Indoor conditions drive the windows state and change times."""

    def test_cool_night_opens_windows_for_a_warm_house(self):
        """Free cooling now, then fresh air, then close when it gets hot."""
        calc = make_calculator(
            hourly(COOL_NIGHT, COOL_NIGHT, NICE, HOT, HOT),
            outdoor=COOL_NIGHT,
            indoor=WARM_HOUSE,
        )
        assert calc.refresh_state()
        assert calc.get_calculated(Calculated.CAN_OPEN_WINDOWS) is True
        assert calc.extra_attributes[ATTR_REASON] is Advice.FREE_COOLING
        assert calc.get_calculated(Calculated.CLOSE_WINDOWS_AT) == hour(4)
        assert calc.get_calculated(Calculated.OPEN_WINDOWS_AT) is None

    def test_same_weather_stays_closed_for_a_cool_house(self):
        """The same cool night doesn't open windows when the house isn't warm."""
        calc = make_calculator(
            hourly(COOL_NIGHT, COOL_NIGHT, NICE, HOT, HOT),
            outdoor=COOL_NIGHT,
            indoor=COOL_HOUSE,
        )
        assert calc.refresh_state()
        assert calc.get_calculated(Calculated.CAN_OPEN_WINDOWS) is False
        assert calc.extra_attributes[ATTR_REASON] is Advice.UNCOMFORTABLE
        assert calc.get_calculated(Calculated.OPEN_WINDOWS_AT) == hour(3)
        assert calc.get_calculated(Calculated.CLOSE_WINDOWS_AT) == hour(4)

    def test_indoor_change_triggers_refresh(self):
        """A new indoor reading recalculates the advice."""
        calc = make_calculator(hourly(NICE), outdoor=COOL_NIGHT, indoor=COOL_HOUSE)
        assert calc.refresh_state()
        assert calc.get_calculated(Calculated.CAN_OPEN_WINDOWS) is False
        calc.update_input(Input.INDOOR_TEMPERATURE, WARM_HOUSE[0])
        calc.update_input(Input.INDOOR_HUMIDITY, WARM_HOUSE[1])
        assert calc.refresh_state()
        assert calc.get_calculated(Calculated.CAN_OPEN_WINDOWS) is True


class TestTimePassing:
    """Results are recalculated as forecast hours pass, without input changes."""

    def test_no_recalculation_before_next_forecast_hour(self, clock: Clock):
        """Nothing is recalculated until the first forecast hour arrives."""
        calc = make_calculator(hourly(NICE, NICE, HOT))
        assert calc.refresh_state()
        clock.now = hour(1) - timedelta(seconds=1)
        assert not calc.refresh_state()

    def test_recalculates_when_forecast_hour_arrives(self, clock: Clock):
        """Reaching the first forecast hour triggers a recalculation."""
        calc = make_calculator(hourly(NICE, NICE, HOT))
        assert calc.refresh_state()
        clock.now = hour(1)
        assert calc.refresh_state()

    def test_change_times_never_in_the_past(self, clock: Clock):
        """Once the close time passes, the next change time is used."""
        calc = make_calculator(hourly(NICE, NICE, HOT, NICE, HOT), outdoor=NICE)
        assert calc.refresh_state()
        assert calc.get_calculated(Calculated.CLOSE_WINDOWS_AT) == hour(3)

        # The outdoor sensor still reads NICE after the forecast said HOT, so the
        # forecast is running warm and is corrected cooler: hour 4 (NICE) becomes
        # too cool, which is the next change.
        clock.now = hour(3) + timedelta(minutes=1)
        assert calc.refresh_state()
        assert calc.get_calculated(Calculated.CAN_OPEN_WINDOWS) is True
        assert calc.get_calculated(Calculated.CLOSE_WINDOWS_AT) == hour(4)
        assert calc.get_calculated(Calculated.CLOSE_WINDOWS_AT) > clock.now

    def test_stale_forecast_clears_outputs(self, clock: Clock):
        """When every forecast hour has passed, outputs become unavailable."""
        calc = make_calculator(hourly(NICE, NICE))
        assert calc.refresh_state()
        clock.now = hour(3)
        assert calc.refresh_state()
        assert not calc.available


# Outdoor samples (°F, %) around the 85 simmer index maximum: SSI(t, 40%) ≈ 1.3266·t − 18.93
SSI_84 = (77.6, 40.0)
SSI_85_5 = (78.72, 40.0)  # past the maximum, within the 1°F margin
SSI_86_5 = (79.48, 40.0)  # past the maximum by more than the margin

COOL_INDOOR = Indoor(temperature=72.0, simmer_index=75.0, enthalpy=40.0)
WARM_INDOOR = Indoor(temperature=80.0, simmer_index=90.0, enthalpy=41.0)


def advise_values(  # pylint: disable=too-many-arguments
    *,
    is_open: bool,
    indoor: Indoor = COOL_INDOOR,
    temp: float = 72.0,
    humidity: float = 50.0,
    dew_point: float = 50.0,
    simmer_index: float = 78.0,
    enthalpy: float = 40.0,
) -> Advice:
    """Advise for explicit values, with the default margins (1°F, 2%)."""
    return make_calculator().advise(
        temp, humidity, dew_point, simmer_index, enthalpy, 0, indoor, is_open=is_open
    )


class TestHysteresis:
    """Once open, windows close only when a limit is passed by the margin."""

    @pytest.mark.parametrize(
        ("change", "within_margin", "beyond_margin"),
        [
            ("simmer_index", 85.5, 86.5),  # maximum 85
            ("simmer_index", 69.5, 68.5),  # minimum 70
            ("dew_point", 60.5, 61.5),  # maximum 60
            ("humidity", 96.0, 97.5),  # maximum 95, margin 2%
        ],
    )
    def test_comfort_limits(self, change, within_margin, beyond_margin):
        """Comfort limits are widened by the margin while open."""
        assert advise_values(is_open=False, **{change: within_margin}) is Advice.UNCOMFORTABLE
        assert advise_values(is_open=True, **{change: within_margin}) is Advice.FRESH_AIR
        assert advise_values(is_open=True, **{change: beyond_margin}) is Advice.UNCOMFORTABLE

    def test_adds_heat(self):
        """The heat tolerance is widened by the margin (~0.56 kJ/kg per °F) while open."""
        # tolerance 1.118 kJ/kg (2°F); margin 0.559 kJ/kg (1°F)
        within = WARM_INDOOR.enthalpy + 1.118 + 0.3
        beyond = WARM_INDOOR.enthalpy + 1.118 + 0.6
        assert advise_values(is_open=False, indoor=WARM_INDOOR, enthalpy=within) is (
            Advice.ADDS_HEAT
        )
        assert advise_values(is_open=True, indoor=WARM_INDOOR, enthalpy=within) is (
            Advice.FRESH_AIR
        )
        assert advise_values(is_open=True, indoor=WARM_INDOOR, enthalpy=beyond) is (
            Advice.ADDS_HEAT
        )

    def test_adds_chill(self):
        """The chill tolerance is widened by the margin while open."""
        # indoor 72°F, tolerance 2°F, margin 1°F
        assert advise_values(is_open=False, temp=69.5) is Advice.ADDS_CHILL
        assert advise_values(is_open=True, temp=69.5) is Advice.FRESH_AIR
        assert advise_values(is_open=True, temp=68.5) is Advice.ADDS_CHILL

    def test_free_cooling_floor(self):
        """The free cooling floor is lowered by the margin while open."""
        cool_night = {"indoor": WARM_INDOOR, "simmer_index": 60.0, "enthalpy": 30.0}
        assert advise_values(is_open=False, temp=59.5, **cool_night) is Advice.UNCOMFORTABLE
        assert advise_values(is_open=True, temp=59.5, **cool_night) is Advice.FREE_COOLING
        assert advise_values(is_open=True, temp=58.5, **cool_night) is Advice.UNCOMFORTABLE

    @pytest.mark.parametrize(
        ("change", "within_margin", "beyond_margin"),
        [
            ("enthalpy", 41.3, 41.7),  # indoor 41.0 kJ/kg, margin 0.559
            ("temp", 80.5, 81.5),  # indoor 80°F, margin 1°F
        ],
    )
    def test_free_cooling_comparisons(self, change, within_margin, beyond_margin):
        """Free cooling's indoor/outdoor comparisons are widened by the margin while open."""
        cool_night = {"indoor": WARM_INDOOR, "temp": 64.0, "simmer_index": 60.0, "enthalpy": 30.0}
        assert advise_values(is_open=False, **cool_night | {change: within_margin}) is (
            Advice.UNCOMFORTABLE
        )
        assert advise_values(is_open=True, **cool_night | {change: within_margin}) is (
            Advice.FREE_COOLING
        )
        assert advise_values(is_open=True, **cool_night | {change: beyond_margin}) is (
            Advice.UNCOMFORTABLE
        )

    def test_free_cooling_continues_past_target(self):
        """Free cooling stops once the house is below the target by the margin."""
        cool_night = {"temp": 64.0, "simmer_index": 66.0, "enthalpy": 30.0}
        nearly_cooled = Indoor(temperature=72.0, simmer_index=77.0, enthalpy=40.0)
        cooled = Indoor(temperature=71.0, simmer_index=76.0, enthalpy=39.0)
        assert advise_values(is_open=False, indoor=nearly_cooled, **cool_night) is (
            Advice.UNCOMFORTABLE
        )
        assert advise_values(is_open=True, indoor=nearly_cooled, **cool_night) is (
            Advice.FREE_COOLING
        )
        assert advise_values(is_open=True, indoor=cooled, **cool_night) is Advice.UNCOMFORTABLE

    def test_no_margin_configured(self):
        """With zero margins, opening and closing use the same limits."""
        calc = make_calculator(config=CONFIG_F | {CONF_HYSTERESIS: 0.0})
        assert calc.advise(72.0, 50.0, 50.0, 85.5, 40.0, 0, COOL_INDOOR, is_open=True) is (
            Advice.UNCOMFORTABLE
        )

    def test_live_readings_creeping_past_the_limit(self):
        """Readings drifting just past the maximum don't flip the windows back and forth."""
        calc = make_calculator(hourly(SSI_84), outdoor=SSI_84)

        def read(sample: tuple[float, float]) -> bool:
            calc.update_input(Input.OUTDOOR_TEMPERATURE, sample[0])
            calc.update_input(Input.OUTDOOR_HUMIDITY, sample[1])
            calc.refresh_state()
            return calc.get_calculated(Calculated.CAN_OPEN_WINDOWS)

        assert calc.refresh_state()
        assert calc.get_calculated(Calculated.CAN_OPEN_WINDOWS) is True
        assert read(SSI_85_5) is True  # within the margin: stays open
        assert read(SSI_86_5) is False  # beyond the margin: closes
        assert read(SSI_85_5) is False  # within the margin: stays closed
        assert read(SSI_84) is True  # back within the limit: opens

    def test_forecast_close_time_follows_hysteresis(self):
        """Forecast hours carry the windows state, so the close time matches the live advice."""
        calc = make_calculator(hourly(SSI_84, SSI_85_5, SSI_85_5, SSI_86_5), outdoor=SSI_84)
        assert calc.refresh_state()
        assert calc.get_calculated(Calculated.CAN_OPEN_WINDOWS) is True
        assert calc.get_calculated(Calculated.CLOSE_WINDOWS_AT) == hour(4)

    def test_forecast_carries_state_between_hours(self):
        """An hour that opens the windows keeps them open through the next, within the margin."""
        calc = make_calculator(hourly(SSI_84, SSI_85_5, SSI_86_5, start=4), outdoor=SSI_86_5)
        assert calc.refresh_state()
        assert calc.get_calculated(Calculated.CAN_OPEN_WINDOWS) is False
        assert calc.get_calculated(Calculated.OPEN_WINDOWS_AT) == hour(4)
        assert calc.get_calculated(Calculated.CLOSE_WINDOWS_AT) == hour(6)

    def test_forecast_open_time_follows_hysteresis(self):
        """While closed, hours within the margin don't count as an opening."""
        calc = make_calculator(hourly(SSI_85_5, SSI_85_5, SSI_84), outdoor=SSI_86_5)
        assert calc.refresh_state()
        assert calc.get_calculated(Calculated.CAN_OPEN_WINDOWS) is False
        assert calc.get_calculated(Calculated.OPEN_WINDOWS_AT) == hour(3)

    def test_starts_closed_after_outputs_were_cleared(self):
        """After an input outage, the strict limits apply again."""
        calc = make_calculator(hourly(SSI_85_5), outdoor=SSI_84)
        assert calc.refresh_state()
        calc.update_input(Input.OUTDOOR_TEMPERATURE, None)
        assert calc.refresh_state()
        calc.update_input(Input.OUTDOOR_TEMPERATURE, SSI_85_5[0])
        assert calc.refresh_state()
        assert calc.get_calculated(Calculated.CAN_OPEN_WINDOWS) is False


class TestHysteresisSettings:
    """The margins are converted and defaulted like the other settings."""

    def test_defaults_for_older_entries(self):
        """Entries saved before these settings existed use 1°F and 2%."""
        margins = make_calculator()._open_margins  # pylint: disable=protected-access
        assert margins.temperature == pytest.approx(1.0)
        assert margins.enthalpy == pytest.approx(0.559, abs=0.001)
        assert margins.humidity == 2

    def test_defaults_converted_to_metric(self):
        """The temperature margin is a difference: 1°F is 0.56°C."""
        calc = make_calculator(unit_system=METRIC_SYSTEM)
        margins = calc._open_margins  # pylint: disable=protected-access
        assert margins.temperature == pytest.approx(0.556, abs=0.001)
        assert margins.enthalpy == pytest.approx(0.559, abs=0.001)

    def test_saved_settings(self):
        """Saved margins are used, the temperature one converted as a difference."""
        config = CONFIG_F | {CONF_HYSTERESIS: 9.0, CONF_HUMIDITY_HYSTERESIS: 5.0}
        calc = make_calculator(config=config, unit_system=METRIC_SYSTEM)
        margins = calc._open_margins  # pylint: disable=protected-access
        assert margins.temperature == pytest.approx(5.0)
        assert margins.humidity == 5.0


class TestForecastCorrection:
    """The forecast is shifted by how far the outdoor sensor is from it right now."""

    def offsets(self, forecast, outdoor, config=None, unit_system=US_CUSTOMARY_SYSTEM):
        """Return the offsets for an outdoor (temperature, humidity) sample."""
        calc = make_calculator(config=config, unit_system=unit_system)
        unit = calc._temp_unit  # pylint: disable=protected-access
        return calc.forecast_offsets(forecast, outdoor[0], calc_dew_point(*outdoor, unit))

    def test_interpolates_between_forecast_hours(self, clock: Clock):
        """The forecast at now is interpolated between the hours around it."""
        forecast = hourly((70.0, 50.0), (80.0, 50.0), start=0)
        clock.now = hour(0) + timedelta(minutes=30)
        offsets = self.offsets(forecast, (77.0, 50.0))
        assert offsets.temperature == pytest.approx(2.0)

    def test_uses_nearest_hour_within_an_hour(self):
        """With no earlier hour, the next hour (within an hour) is used."""
        offsets = self.offsets(hourly((70.0, 50.0)), (73.0, 50.0))
        assert offsets.temperature == pytest.approx(3.0)
        assert offsets.dew_point == pytest.approx(
            calc_dew_point(73.0, 50.0, "°F") - calc_dew_point(70.0, 50.0, "°F")
        )

    def test_no_correction_without_a_nearby_hour(self):
        """No forecast hour within an hour of now means no correction."""
        offsets = self.offsets(hourly(NICE, start=2), (90.0, 50.0))
        assert offsets == comfort_module.NO_OFFSETS

    def test_skips_incomplete_hours(self):
        """Hours missing temperature or humidity aren't used."""
        forecast = hourly((70.0, 50.0), start=0) + hourly((80.0, 50.0))
        forecast[1]["humidity"] = None
        offsets = self.offsets(forecast, (72.0, 50.0))
        assert offsets.temperature == pytest.approx(2.0)

    def test_limited_to_10_fahrenheit(self):
        """A large difference (e.g. a sun-heated sensor) is limited to 10°F."""
        offsets = self.offsets(hourly((70.0, 40.0)), (95.0, 40.0))
        assert offsets.temperature == pytest.approx(10.0)
        offsets = self.offsets(hourly((70.0, 40.0)), (45.0, 40.0))
        assert offsets.temperature == pytest.approx(-10.0)

    def test_limit_converted_to_celsius(self):
        """The 10°F limit is a temperature difference: 5.56°C."""
        offsets = self.offsets(hourly((20.0, 40.0)), (35.0, 40.0), unit_system=METRIC_SYSTEM)
        assert offsets.temperature == pytest.approx(5.556, abs=0.001)

    def test_correction_fades_over_three_hours(self):
        """Hours 1, 2 and 3 get 2/3, 1/3 and none of the offset."""
        forecast = hourly(*[(70.0, 50.0)] * 4)
        offsets = comfort_module.ForecastOffsets(temperature=3.0, dew_point=0.0)
        result = make_calculator().make_comfort_forecast(forecast, INDOOR, offsets=offsets)
        assert [e.temperature for e in result] == pytest.approx([72.0, 71.0, 70.0, 70.0])

    def test_humidity_recalculated_from_corrected_values(self):
        """Corrected temperature and dew point give a consistent humidity."""
        forecast = hourly((70.0, 50.0))
        offsets = comfort_module.ForecastOffsets(temperature=3.0, dew_point=1.5)
        (entry,) = make_calculator().make_comfort_forecast(forecast, INDOOR, offsets=offsets)
        dew_point = calc_dew_point(70.0, 50.0, "°F") + 1.0  # 2/3 of 1.5
        assert entry.temperature == pytest.approx(72.0)
        assert entry.dew_point == pytest.approx(dew_point)
        assert entry.simmer_index == pytest.approx(
            calc_simmer_index(72.0, calc_relative_humidity(72.0, dew_point, "°F"), "°F")
        )

    def test_dew_point_never_above_temperature(self):
        """A dew point corrected above the temperature is limited to it (100%)."""
        forecast = hourly((60.0, 95.0))
        offsets = comfort_module.ForecastOffsets(temperature=0.0, dew_point=9.0)
        (entry,) = make_calculator().make_comfort_forecast(forecast, INDOOR, offsets=offsets)
        assert entry.dew_point == pytest.approx(entry.temperature)

    def test_offsets_published(self):
        """The offsets are published, rounded to 0.1."""
        calc = make_calculator(hourly((70.0, 50.0)), outdoor=(72.04, 50.0))
        assert calc.refresh_state()
        assert calc.get_calculated(Calculated.FORECAST_TEMPERATURE_OFFSET) == 2.0
        assert calc.get_calculated(Calculated.FORECAST_DEW_POINT_OFFSET) == round(
            calc_dew_point(72.04, 50.0, "°F") - calc_dew_point(70.0, 50.0, "°F"), 1
        )

    def test_no_offsets_when_sensor_matches_forecast(self):
        """A sensor agreeing with the forecast leaves it unchanged."""
        calc = make_calculator(hourly(NICE, HOT), outdoor=NICE)
        assert calc.refresh_state()
        assert calc.get_calculated(Calculated.FORECAST_TEMPERATURE_OFFSET) == 0.0
        assert calc.get_calculated(Calculated.CLOSE_WINDOWS_AT) == hour(2)

    def test_warmer_sensor_moves_open_time_later(self):
        """If it's warmer here than forecast, the forecast cool-down comes later."""
        # Forecast: hot now, cooling to comfortable at hours 1 and 2.
        forecast = hourly(HOT, NICE, NICE, NICE, start=0)
        calc = make_calculator(forecast, outdoor=HOT)
        assert calc.refresh_state()
        assert calc.get_calculated(Calculated.OPEN_WINDOWS_AT) == hour(1)

        # The sensor reads 12°F warmer than forecast (limited to 10°F): hour 1 is
        # corrected +6.7°F (simmer index 85.7, too warm), hour 2 +3.3°F (81.1).
        calc = make_calculator(forecast, outdoor=(HOT[0] + 12, HOT[1]))
        assert calc.refresh_state()
        assert calc.get_calculated(Calculated.OPEN_WINDOWS_AT) == hour(2)
