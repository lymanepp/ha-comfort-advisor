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
    CONF_HUMIDITY_MAX,
    CONF_POLLEN_MAX,
    CONF_SIMMER_INDEX_MAX,
    CONF_SIMMER_INDEX_MIN,
    CONF_TEMPERATURE_TOLERANCE,
    CONF_WEATHER,
)
from custom_components.comfort_advisor.formulas import (
    calc_dew_point,
    calc_moist_air_enthalpy,
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
        """Only entries from now through the next 24 hours are used."""
        forecast = hourly(*[NICE] * 30, start=-3)
        result = make_calculator().make_comfort_forecast(forecast, INDOOR)
        assert result[0].time == hour(0)
        assert result[-1].time == hour(24)
        assert len(result) == 25

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
        assert calc.get_calculated(Calculated.CAN_OPEN_WINDOWS) == "on"

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
        # 41.59 vs 41.23 kJ/kg; 1°F is worth about 0.56 kJ/kg
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
        """Entries saved before these settings existed use 60°F and 1°F."""
        assert CONF_COOLING_TEMPERATURE_MIN not in CONFIG_F
        calc = make_calculator()
        assert calc._cooling_temp_min == pytest.approx(60.0)  # pylint: disable=protected-access
        assert calc._temp_tolerance == pytest.approx(1.0)  # pylint: disable=protected-access

    def test_defaults_converted_to_metric(self):
        """Defaults are converted to °C on a metric system."""
        calc = make_calculator(unit_system=METRIC_SYSTEM)
        # pylint: disable=protected-access
        assert calc._cooling_temp_min == pytest.approx(15.56, abs=0.01)
        assert calc._temp_tolerance == pytest.approx(0.556, abs=0.001)
        assert calc._enthalpy_tolerance == pytest.approx(0.559, abs=0.001)

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
        assert calc.get_calculated(Calculated.CAN_OPEN_WINDOWS) == "on"
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
        assert calc.get_calculated(Calculated.CAN_OPEN_WINDOWS) == "off"
        assert calc.extra_attributes[ATTR_REASON] is Advice.UNCOMFORTABLE
        assert calc.get_calculated(Calculated.OPEN_WINDOWS_AT) == hour(3)
        assert calc.get_calculated(Calculated.CLOSE_WINDOWS_AT) == hour(4)

    def test_indoor_change_triggers_refresh(self):
        """A new indoor reading recalculates the advice."""
        calc = make_calculator(hourly(NICE), outdoor=COOL_NIGHT, indoor=COOL_HOUSE)
        assert calc.refresh_state()
        assert calc.get_calculated(Calculated.CAN_OPEN_WINDOWS) == "off"
        calc.update_input(Input.INDOOR_TEMPERATURE, WARM_HOUSE[0])
        calc.update_input(Input.INDOOR_HUMIDITY, WARM_HOUSE[1])
        assert calc.refresh_state()
        assert calc.get_calculated(Calculated.CAN_OPEN_WINDOWS) == "on"


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

        # The outdoor sensor still reads NICE after the forecast said HOT.
        clock.now = hour(3) + timedelta(minutes=1)
        assert calc.refresh_state()
        assert calc.get_calculated(Calculated.CAN_OPEN_WINDOWS) == "on"
        assert calc.get_calculated(Calculated.CLOSE_WINDOWS_AT) == hour(5)
        assert calc.get_calculated(Calculated.CLOSE_WINDOWS_AT) > clock.now

    def test_stale_forecast_clears_outputs(self, clock: Clock):
        """When every forecast hour has passed, outputs become unavailable."""
        calc = make_calculator(hourly(NICE, NICE))
        assert calc.refresh_state()
        clock.now = hour(3)
        assert calc.refresh_state()
        assert not calc.available
