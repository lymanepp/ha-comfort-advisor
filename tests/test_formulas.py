"""Tests for the psychrometric formulas used by the comfort calculation."""

from homeassistant.const import UnitOfPressure, UnitOfTemperature
from homeassistant.util.unit_conversion import TemperatureConverter as TC
import pytest

from custom_components.comfort_advisor.formulas import (
    calc_dew_point,
    calc_moist_air_enthalpy,
    calc_simmer_index,
    dew_point_from_relative_humidity,
    moist_air_enthalpy_from_relative_humidity,
    relative_humidity_from_dew_point,
    saturation_vapor_pressure,
    summer_simmer_index,
)

C = UnitOfTemperature.CELSIUS
F = UnitOfTemperature.FAHRENHEIT


@pytest.mark.parametrize(
    ("temp_c", "expected_pa"),
    [
        # ASHRAE Fundamentals 2021, chapter 1, table 3
        (-10, 259.87),  # over ice
        (0, 611.21),
        (20, 2339.2),
        (40, 7385.1),
    ],
)
def test_saturation_vapor_pressure_matches_ashrae_table(temp_c, expected_pa):
    """Saturation pressure matches ASHRAE tabulated values."""
    assert saturation_vapor_pressure(temp_c) == pytest.approx(expected_pa, rel=5e-4)


def test_saturation_vapor_pressure_increases_with_temperature():
    """Saturation pressure rises with temperature."""
    values = [saturation_vapor_pressure(t) for t in range(-30, 50, 5)]
    assert values == sorted(values)


@pytest.mark.parametrize(
    ("temp_c", "rh", "expected_dew_point_c"),
    [
        (25, 50, 13.86),
        (20, 60, 12.0),
        (30, 80, 26.2),
        (10, 30, -6.8),
    ],
)
def test_dew_point_reference_values(temp_c, rh, expected_dew_point_c):
    """Dew point matches reference values."""
    assert dew_point_from_relative_humidity(temp_c, rh) == pytest.approx(
        expected_dew_point_c, abs=0.15
    )


@pytest.mark.parametrize("temp_c", [0, 15, 30])
def test_dew_point_equals_temperature_at_saturation(temp_c):
    """At 100% humidity the dew point is the air temperature."""
    assert dew_point_from_relative_humidity(temp_c, 100) == pytest.approx(temp_c, abs=0.05)


@pytest.mark.parametrize(("temp_c", "rh"), [(25, 50), (5, 90), (35, 20)])
def test_dew_point_and_relative_humidity_round_trip(temp_c, rh):
    """Humidity -> dew point -> humidity returns the original value."""
    dew_point = dew_point_from_relative_humidity(temp_c, rh)
    assert relative_humidity_from_dew_point(temp_c, dew_point) == pytest.approx(rh, rel=5e-3)


def test_calc_dew_point_converts_units():
    """Dew point is the same in °C and °F."""
    dew_point_c = calc_dew_point(25, 50, C)
    dew_point_f = calc_dew_point(77, 50, F)
    assert dew_point_f == pytest.approx(TC.convert(dew_point_c, C, F), abs=0.02)


def test_enthalpy_reference_value():
    """Enthalpy matches a hand-calculated ASHRAE value."""
    # W = 0.621945 * 1.5846 / (101.325 - 1.5846) = 0.009881 kg/kg
    # h = 1.006 * 25 + 0.009881 * (2501 + 1.86 * 25) = 50.32 kJ/kg
    assert moist_air_enthalpy_from_relative_humidity(25, 50, 101.325) == pytest.approx(
        50.32, abs=0.01
    )


def test_enthalpy_of_dry_air_is_sensible_heat_only():
    """Dry air enthalpy is just the sensible heat term."""
    assert moist_air_enthalpy_from_relative_humidity(25, 0, 101.325) == pytest.approx(1.006 * 25)


def test_enthalpy_increases_with_humidity():
    """Enthalpy rises with humidity."""
    values = [
        moist_air_enthalpy_from_relative_humidity(25, rh, 101.325) for rh in range(0, 101, 10)
    ]
    assert values == sorted(values)


def test_calc_moist_air_enthalpy_converts_units():
    """Enthalpy is the same from metric and imperial inputs."""
    metric = calc_moist_air_enthalpy(25, 50, 101.325, C, UnitOfPressure.KPA)
    imperial = calc_moist_air_enthalpy(77, 50, 101_325, F, UnitOfPressure.PA)
    assert imperial == pytest.approx(metric)


@pytest.mark.parametrize("rh", [0, 20, 50, 90, 100])
def test_simmer_index_is_independent_of_humidity_at_58f(rh):
    """Humidity has no effect on the simmer index at 58°F."""
    # The humidity term is multiplied by (tf - 58), so it drops out at 58°F.
    assert summer_simmer_index(58, rh) == pytest.approx(58.01)


@pytest.mark.parametrize(
    ("tf", "rh", "expected"),
    [
        (70, 50, 75.24),
        (75, 50, 82.41),
        (80, 50, 89.59),
        (85, 30, 90.89),
    ],
)
def test_simmer_index_reference_values(tf, rh, expected):
    """Simmer index matches hand-calculated values."""
    assert summer_simmer_index(tf, rh) == pytest.approx(expected, abs=0.01)


def test_simmer_index_increases_with_humidity_above_58f():
    """Above 58°F more humidity means a higher simmer index."""
    values = [summer_simmer_index(80, rh) for rh in range(0, 101, 10)]
    assert values == sorted(values)


def test_calc_simmer_index_converts_units():
    """Simmer index is the same in °C and °F."""
    assert calc_simmer_index(25, 50, C) == pytest.approx(
        TC.convert(summer_simmer_index(77, 50), F, C)
    )
