"""Weather formulas."""
from __future__ import annotations

from enum import IntEnum
import math
from typing import cast

from homeassistant.const import UnitOfPressure, UnitOfTemperature
from homeassistant.util.unit_conversion import PressureConverter as PC
from homeassistant.util.unit_conversion import TemperatureConverter as TC

# pylint: disable=invalid-name

CELSIUS_TO_KELVIN = 273.15


def saturation_vapor_pressure(t: float) -> float:
    """Calculate water vapor saturation pressure.

    Arguments:
    t - temperature [°C]

    Returns:
    Saturation vapor pressure [Pa]
    """

    # ASHRAE fundamentals 2021 pg 1.5
    c1 = -5.6745359e03
    c2 = 6.3925247e00
    c3 = -9.6778430e-03
    c4 = 6.2215701e-07
    c5 = 2.0747825e-09
    c6 = -9.4840240e-13
    c7 = 4.1635019e00
    c8 = -5.8002206e03
    c9 = 1.3914993e00
    c10 = -4.8640239e-02
    c11 = 4.1764768e-05
    c12 = -1.4452093e-08
    c13 = 6.5459673e00

    T = t + CELSIUS_TO_KELVIN

    return (
        # ASHRAE fundamentals 2021 pg 1.5 eq 5
        math.exp(c1 / T + c2 + c3 * T + c4 * T**2 + c5 * T**3 + c6 * T**4 + c7 * math.log(T))
        if t < 0
        # ASHRAE fundamentals 2021 pg 1.5 eq 6
        else math.exp(c8 / T + c9 + c10 * T + c11 * T**2 + c12 * T**3 + c13 * math.log(T))
    )


def humidity_ratio_from_vapor_pressure(p: float, p_w: float):
    """Calculate humidity ratio from vapor pressure.

    Arguments:
    p - total pressure of moist air [kPa]
    p_w - partial pressure of water vapor in moist air [kPa]

    Returns:
    Humidity ratio of moist air [kg_w/kg_da]
    """

    # ASHRAE fundamentals 2021 pg 1.9 eq 20
    return 0.621945 * p_w / (p - p_w)


def vapor_pressure_from_relative_humidity(p_ws: float, rh: float):
    """Calculate vapor pressure from relative humidity.

    Arguments:
    p_ws - pressure of saturated pure water [kPa]
    rh - relative humidity [%]

    Returns:
    Humidity ratio of moist air [kg_w/kg_da]
    """

    # ASHRAE fundamentals 2021 pg 1.9 eq 22
    return rh / 100 * p_ws


def relative_humidity_from_dew_point(t: float, t_d: float):
    """Calculate relative humidity from temperature and dew-point.

    Arguments:
    t - dry-bulb temperature of moist air [°C]
    t_d - dew-point temperature of moist air [°C]

    Returns:
    Relative humidity [%]
    """

    # ASHRAE fundamentals 2021 pg 1.9 eq 22
    return saturation_vapor_pressure(t_d) / saturation_vapor_pressure(t) * 100


def moist_air_enthalpy_from_humidity_ratio(t, W):
    """Calculate moist air enthalpy from temperature and humidity ratio.

    Arguments:
    t - temperature [°C]
    W - humidity ratio [kg_w/kg_da]

    Returns:
    Specific enthalpy of moist air [kJ/kg_da]
    """

    # calculate enthalpy (ASHRAE fundamentals 2021 pg 1.10 eq 30)
    return 1.006 * t + W * (2501 + 1.86 * t)


def absolute_humidity_from_relative_humidity(t: float, rh: float):
    # https://carnotcycle.wordpress.com/2012/08/04/how-to-convert-relative-humidity-to-absolute-humidity
    return (6.122 * math.exp((17.67 * t) / (243.5 + t)) * rh * 2.1674) / (t + CELSIUS_TO_KELVIN)


def dew_point_from_relative_humidity(t: float, rh: float):
    # https://pon.fr/dzvents-alerte-givre-et-calcul-humidite-absolue
    A0 = 373.15 / (273.15 + t)
    SUM = (
        -7.90298 * (A0 - 1)
        + 5.02808 * math.log(A0, 10)
        + -1.3816e-7 * (10 ** (11.344 * (1 - 1 / A0)) - 1)
        + 8.1328e-3 * (10 ** (-3.49149 * (A0 - 1)) - 1)
        + math.log(1013.246, 10)
    )
    vp = 10 ** (SUM - 3) * rh
    t_d = math.log(vp / 0.61078)
    t_d = (241.88 * t_d) / (17.558 - t_d)
    return t_d


def heat_index_from_relative_humidity(tf: float, rh: float) -> float:
    """Calculate heat index from temperature and relative humidity.

    Arguments:
    tf - dry-bulb temperature [°F]
    rh - relative humidity [%]

    Returns:
    Heat index [°F]
    """

    # http://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml
    hi = 0.5 * (tf + 61.0 + ((tf - 68.0) * 1.2) + (rh * 0.094))
    if ((tf + hi) / 2) >= 80:
        hi = (
            -42.379
            + (2.04901523 * tf)
            + (10.14333127 * rh)
            + (-0.22475541 * tf * rh)
            + (-0.00683783 * tf**2)
            + (-0.05481717 * rh**2)
            + (0.00122874 * tf**2 * rh)
            + (0.00085282 * tf * rh**2)
            + (-0.00000199 * tf**2 * rh**2)
        )
        if rh < 13 and 80 <= tf <= 112:
            hi -= ((13 - rh) / 4) * math.sqrt((17 - abs(tf - 95)) / 17)
        elif rh > 85 and 80 <= tf <= 87:
            hi += ((rh - 85) / 10) * ((87 - tf) / 5)
    return hi


def summer_simmer_index(tf: float, rh: float):
    """Calculate summer simmer index from temperature and relative humidity.

    Arguments:
    tf - dry-bulb temperature [°F]
    rh - relative humidity [%]

    Returns:
    Summer simmer index [°F]
    """

    # https://www.vcalc.com/wiki/rklarsen/Summer+Simmer+Index
    return 1.98 * (tf - (0.55 - (0.0055 * rh)) * (tf - 58)) - 56.83


def frost_point(t: float, t_d: float) -> float:
    """Calculate frost-point from temperature and dew-point.

    Arguments:
    t - dry-bulb temperature [°C]
    t_d - dew-point temperature [°C]

    Returns:
    frost-point temperature [°C]
    """

    # https://pon.fr/dzvents-alerte-givre-et-calcul-humidite-absolue
    T = t + CELSIUS_TO_KELVIN
    Td = t_d + CELSIUS_TO_KELVIN
    Tfp = Td + (2671.02 / ((2954.61 / T) + 2.193665 * math.log(T) - 13.3448)) - T
    return Tfp - CELSIUS_TO_KELVIN


def moist_air_enthalpy_from_relative_humidity(t: float, rh: float, p: float):
    """Calculate the specific enthalpy of moist air from relative humidity.

    Arguments:
    t - temperature [°C]
    rh - relative humidity [%]
    p - total pressure of moist air [kPa]

    Returns:
    Specific enthalpy of moist air [kJ/kg_da]
    """

    p_ws = saturation_vapor_pressure(t) / 1_000  # convert to kPa
    p_w = vapor_pressure_from_relative_humidity(p_ws, rh)
    W = humidity_ratio_from_vapor_pressure(p, p_w)
    return moist_air_enthalpy_from_humidity_ratio(t, W)


class FrostRisk(IntEnum):
    """Risk of frost formation."""

    NO_RISK = 0
    UNLIKELY = 1
    PROBABLE = 2
    HIGHLY_PROBABLE = 3


def calc_relative_humidity(temp: float, dew_point: float, temp_unit: str) -> float:
    """Calculate relative humidity from temperature and dew-point."""

    t = TC.convert(temp, temp_unit, UnitOfTemperature.CELSIUS)
    t_d = TC.convert(dew_point, temp_unit, UnitOfTemperature.CELSIUS)

    return relative_humidity_from_dew_point(t, t_d)


def calc_dew_point(temp: float, rh: float, temp_unit: str) -> float:
    """Calculate dew-point from temperature and humidity."""
    t = TC.convert(temp, temp_unit, UnitOfTemperature.CELSIUS)

    t_d = dew_point_from_relative_humidity(t, rh)

    return cast(float, round(TC.convert(t_d, UnitOfTemperature.CELSIUS, temp_unit), 2))


def calc_heat_index(temp: float, rh: float, temp_unit: str) -> float:
    """Calculate heat index from temperature and humidity."""
    tf = TC.convert(temp, temp_unit, UnitOfTemperature.FAHRENHEIT)

    hi = heat_index_from_relative_humidity(tf, rh)

    return cast(float, round(TC.convert(hi, UnitOfTemperature.FAHRENHEIT, temp_unit), 2))


def calc_absolute_humidity(temp: float, rh: float, temp_unit: str) -> float:
    """Calculate absolute humidity from temperature and humidity."""
    t = TC.convert(temp, temp_unit, UnitOfTemperature.CELSIUS)

    abs_hum = absolute_humidity_from_relative_humidity(t, rh)

    return round(abs_hum, 2)


def calc_frost_point(temp: float, rh: float, temp_unit: str) -> float:
    """Calculate frost point from temperature and humidity."""
    t = TC.convert(temp, temp_unit, UnitOfTemperature.CELSIUS)

    t_d = dew_point_from_relative_humidity(t, rh)
    t_fp = frost_point(t, t_d)

    return TC.convert(t_fp, UnitOfTemperature.CELSIUS, temp_unit)


def calc_frost_risk(temp: float, rh: float, temp_unit: str) -> FrostRisk:
    """Calculate frost risk from temperature and humidity."""
    t = TC.convert(temp, temp_unit, UnitOfTemperature.CELSIUS)

    abs_hum = absolute_humidity_from_relative_humidity(t, rh)
    t_d = dew_point_from_relative_humidity(t, rh)
    t_fp = frost_point(t, t_d)

    abs_humidity_threshold = 2.8

    return (
        (FrostRisk.UNLIKELY if abs_hum <= abs_humidity_threshold else FrostRisk.HIGHLY_PROBABLE)
        if t <= 1 and t_fp <= 0
        else (
            FrostRisk.PROBABLE
            if t <= 4 and t_fp <= 0.5 and abs_hum > abs_humidity_threshold
            else FrostRisk.NO_RISK
        )
    )


def calc_simmer_index(temp: float, rh: float, temp_unit: str) -> float:
    """Calculate summer simmer index from temperature and humidity."""
    tf = TC.convert(temp, temp_unit, UnitOfTemperature.FAHRENHEIT)

    ssi = summer_simmer_index(tf, rh)

    return TC.convert(ssi, UnitOfTemperature.FAHRENHEIT, temp_unit)


def calc_moist_air_enthalpy(
    temp: float, rh: float, press: float, temp_unit: str, press_unit: str
) -> float:
    """Calculate moist air enthalpy (kJ/kg) from temperature, humidity [%] and pressure."""

    t = TC.convert(temp, temp_unit, UnitOfTemperature.CELSIUS)
    p = PC.convert(press, press_unit, UnitOfPressure.KPA)

    return moist_air_enthalpy_from_relative_humidity(t, rh, p)
