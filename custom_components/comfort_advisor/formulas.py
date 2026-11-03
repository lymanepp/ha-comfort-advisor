"""Psychrometric and comfort formulas."""

import math

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


def humidity_ratio_from_vapor_pressure(p: float, p_w: float) -> float:
    """Calculate humidity ratio from vapor pressure.

    Arguments:
    p - total pressure of moist air [kPa]
    p_w - partial pressure of water vapor in moist air [kPa]

    Returns:
    Humidity ratio of moist air [kg_w/kg_da]
    """

    # ASHRAE fundamentals 2021 pg 1.9 eq 20
    return 0.621945 * p_w / (p - p_w)


def vapor_pressure_from_relative_humidity(p_ws: float, rh: float) -> float:
    """Calculate vapor pressure from relative humidity.

    Arguments:
    p_ws - pressure of saturated pure water [kPa]
    rh - relative humidity [%]

    Returns:
    Partial pressure of water vapor in moist air [kPa]
    """

    # ASHRAE fundamentals 2021 pg 1.9 eq 22
    return rh / 100 * p_ws


def relative_humidity_from_dew_point(t: float, t_d: float) -> float:
    """Calculate relative humidity from temperature and dew-point.

    Arguments:
    t - dry-bulb temperature of moist air [°C]
    t_d - dew-point temperature of moist air [°C]

    Returns:
    Relative humidity [%]
    """

    # ASHRAE fundamentals 2021 pg 1.9 eq 22
    return saturation_vapor_pressure(t_d) / saturation_vapor_pressure(t) * 100


def moist_air_enthalpy_from_humidity_ratio(t: float, W: float) -> float:
    """Calculate moist air enthalpy from temperature and humidity ratio.

    Arguments:
    t - temperature [°C]
    W - humidity ratio [kg_w/kg_da]

    Returns:
    Specific enthalpy of moist air [kJ/kg_da]
    """

    # calculate enthalpy (ASHRAE fundamentals 2021 pg 1.10 eq 30)
    return 1.006 * t + W * (2501 + 1.86 * t)


def dew_point_from_relative_humidity(t: float, rh: float) -> float:
    """Calculate dew-point [°C] from temperature [°C] and relative humidity [%]."""
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


def summer_simmer_index(tf: float, rh: float) -> float:
    """Calculate summer simmer index from temperature and relative humidity.

    Arguments:
    tf - dry-bulb temperature [°F]
    rh - relative humidity [%]

    Returns:
    Summer simmer index [°F]
    """

    # https://www.vcalc.com/wiki/rklarsen/Summer+Simmer+Index
    return 1.98 * (tf - (0.55 - (0.0055 * rh)) * (tf - 58)) - 56.83


def moist_air_enthalpy_from_relative_humidity(t: float, rh: float, p: float) -> float:
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


def calc_dew_point(temp: float, rh: float, temp_unit: str) -> float:
    """Calculate dew-point from temperature and humidity."""
    t = TC.convert(temp, temp_unit, UnitOfTemperature.CELSIUS)

    t_d = dew_point_from_relative_humidity(t, rh)

    return round(TC.convert(t_d, UnitOfTemperature.CELSIUS, temp_unit), 2)


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
