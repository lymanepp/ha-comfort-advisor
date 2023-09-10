"""Weather formulas."""
from __future__ import annotations

from enum import IntEnum
import math
from typing import cast

from homeassistant.const import UnitOfTemperature
from homeassistant.util.unit_conversion import TemperatureConverter as TC


class FrostRisk(IntEnum):
    """Risk of frost formation."""

    NO_RISK = 0
    UNLIKELY = 1
    PROBABLE = 2
    HIGHLY_PROBABLE = 3


# pylint: disable=invalid-name


def calc_humidity(temp: float, dew_point: float, temp_unit: str) -> float:
    """Calculate relative humidity from temperature and dew point.

    https://www.f5wx.com/pages/calc.htm
    """

    def t_to_e(t: float) -> float:
        return 6.11 * 10 ** ((7.5 * t) / (237.7 + t))

    t_c = TC.convert(temp, temp_unit, UnitOfTemperature.CELSIUS)
    dp_c = TC.convert(dew_point, temp_unit, UnitOfTemperature.CELSIUS)
    return t_to_e(dp_c) / t_to_e(t_c) * 100


def calc_dew_point(temp: float, rh: float, temp_unit: str) -> float:
    """Calculate dew point from temperature and humidity.

    https://pon.fr/dzvents-alerte-givre-et-calcul-humidite-absolue
    """
    t_c = TC.convert(temp, temp_unit, UnitOfTemperature.CELSIUS)
    A0 = 373.15 / (273.15 + t_c)
    SUM = (
        -7.90298 * (A0 - 1)
        + 5.02808 * math.log(A0, 10)
        + -1.3816e-7 * (pow(10, (11.344 * (1 - 1 / A0))) - 1)
        + 8.1328e-3 * (pow(10, (-3.49149 * (A0 - 1))) - 1)
        + math.log(1013.246, 10)
    )
    vp = pow(10, SUM - 3) * rh
    dp_c = math.log(vp / 0.61078)
    dp_c = (241.88 * dp_c) / (17.558 - dp_c)
    return cast(float, round(TC.convert(dp_c, UnitOfTemperature.CELSIUS, temp_unit), 2))


def calc_heat_index(temp: float, rh: float, temp_unit: str) -> float:
    """Calculate heat index from temperature and humidity.

    http://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml
    """
    t_c = TC.convert(temp, temp_unit, UnitOfTemperature.FAHRENHEIT)
    hi = 0.5 * (t_c + 61.0 + ((t_c - 68.0) * 1.2) + (rh * 0.094))
    if ((t_c + hi) / 2) >= 80:
        hi = (
            -42.379
            + (2.04901523 * t_c)
            + (10.14333127 * rh)
            + (-0.22475541 * t_c * rh)
            + (-0.00683783 * t_c * t_c)
            + (-0.05481717 * rh * rh)
            + (0.00122874 * t_c * t_c * rh)
            + (0.00085282 * t_c * rh * rh)
            + (-0.00000199 * t_c * t_c * rh * rh)
        )
        if rh < 13 and 80 <= t_c <= 112:
            hi -= ((13 - rh) * 0.25) * math.sqrt((17 - abs(t_c - 95)) * 0.05882)
        elif rh > 85 and 80 <= t_c <= 87:
            hi += ((rh - 85) * 0.1) * ((87 - t_c) * 0.2)

    return cast(float, round(TC.convert(hi, UnitOfTemperature.FAHRENHEIT, temp_unit), 2))


def calc_absolute_humidity(temp: float, rh: float, temp_unit: str) -> float:
    """Calculate absolute humidity from temperature and humidity.

    https://carnotcycle.wordpress.com/2012/08/04/how-to-convert-relative-humidity-to-absolute-humidity
    """
    t_c = TC.convert(temp, temp_unit, UnitOfTemperature.CELSIUS)
    abs_hum = (6.112 * math.exp((17.67 * t_c) / (243.5 + t_c)) * rh * 2.1674) / (t_c + 273.15)
    return round(abs_hum, 2)  # type: ignore


def calc_frost_point(temp: float, rh: float, temp_unit: str) -> float:
    """Calculate frost point from temperature and humidity.

    https://pon.fr/dzvents-alerte-givre-et-calcul-humidite-absolue
    """
    dp = calc_dew_point(temp, rh, temp_unit)
    t_k = TC.convert(temp, temp_unit, UnitOfTemperature.KELVIN)
    dp_k = TC.convert(dp, temp_unit, UnitOfTemperature.KELVIN)

    frost_point = (
        dp_k + (2671.02 / ((2954.61 / t_k) + 2.193665 * math.log(t_k) - 13.3448)) - t_k
    ) - 273.15

    return cast(float, round(TC.convert(frost_point, UnitOfTemperature.CELSIUS, temp_unit), 2))


def calc_frost_risk(temp: float, rh: float, temp_unit: str) -> FrostRisk:
    """Calculate frost risk from temperature and humidity."""
    abs_hum = calc_absolute_humidity(temp, rh, temp_unit)
    fp = calc_frost_point(temp, rh, temp_unit)

    t_c = TC.convert(temp, temp_unit, UnitOfTemperature.CELSIUS)
    fp_c = TC.convert(fp, temp_unit, UnitOfTemperature.CELSIUS)

    abs_humidity_threshold = 2.8
    if t_c <= 1 and fp_c <= 0:
        return (
            FrostRisk.UNLIKELY if abs_hum <= abs_humidity_threshold else FrostRisk.HIGHLY_PROBABLE
        )

    return (
        FrostRisk.PROBABLE
        if t_c <= 4 and fp_c <= 0.5 and abs_hum > abs_humidity_threshold
        else FrostRisk.NO_RISK
    )


def calc_simmer_index(temp: float, rh: float, temp_unit: str) -> float:
    """Calculate summer simmer index from temperature and humidity.

    https://www.vcalc.com/wiki/rklarsen/Summer+Simmer+Index
    """
    t_f = TC.convert(temp, temp_unit, UnitOfTemperature.FAHRENHEIT)
    ssi = 1.98 * (t_f - (0.55 - (0.0055 * rh)) * (t_f - 58)) - 56.83
    return cast(float, round(TC.convert(ssi, UnitOfTemperature.FAHRENHEIT, temp_unit), 2))


def calc_moist_air_enthalpy(temp: float, rh: float, temp_unit: str) -> float:
    """Calculate moist air enthalpy (kJ/kg) from temperature and humidity."""

    t_c = TC.convert(temp, temp_unit, UnitOfTemperature.CELSIUS)
    t_k = TC.convert(t_c, UnitOfTemperature.CELSIUS, UnitOfTemperature.KELVIN)

    # calculate saturation vapour pressure for temperature
    if t_c < 0:
        vp_saturation = math.exp(
            -5674.5359 / t_k
            + 6.3925247
            + t_k
            * (-0.9677843e-2 + t_k * (0.62215701e-6 + t_k * (0.20747825e-8 + -0.9484024e-12 * t_k)))
            + 4.1635019 * math.log(t_k)
        )
    else:
        vp_saturation = math.exp(
            -5800.2206 / t_k
            + 1.3914993
            + t_k * (-0.048640239 + t_k * (0.41764768e-4 + t_k * -0.14452093e-7))
            + 6.5459673 * math.log(t_k)
        )

    vp = rh / 100 * vp_saturation
    hum_ratio = 0.62198 * vp / (101325 - vp)

    enthalpy_dry_air = 1004 * t_c
    enthalpy_sat_vap = 2501000 + 1805 * t_c
    enthalpy = enthalpy_dry_air + hum_ratio * enthalpy_sat_vap

    return cast(float, round(enthalpy / 1000, 2))
