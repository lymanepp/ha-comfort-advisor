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


def compute_dew_point(temp: float, rh: float, temp_unit: str) -> float:
    """Calculate dew point from temperature and humidity.

    https://pon.fr/dzvents-alerte-givre-et-calcul-humidite-absolue
    """
    T = TC.convert(temp, temp_unit, UnitOfTemperature.CELSIUS)
    b, c = 17.67, 243.5
    gamma = math.log(rh / 100) + b * T / (c + T)
    Td = c * gamma / (b - gamma)
    return cast(float, round(TC.convert(Td, UnitOfTemperature.CELSIUS, temp_unit), 2))


def compute_heat_index(temp: float, rh: float, temp_unit: str) -> float:
    """Calculate heat index from temperature and humidity.

    http://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml
    """
    T = TC.convert(temp, temp_unit, UnitOfTemperature.FAHRENHEIT)
    HI = 0.5 * (T + 61.0 + ((T - 68.0) * 1.2) + (rh * 0.094))
    if ((T + HI) / 2) >= 80:
        HI = (
            -42.379
            + (2.04901523 * T)
            + (10.14333127 * rh)
            + (-0.22475541 * T * rh)
            + (-0.00683783 * T * T)
            + (-0.05481717 * rh * rh)
            + (0.00122874 * T * T * rh)
            + (0.00085282 * T * rh * rh)
            + (-0.00000199 * T * T * rh * rh)
        )
        if rh < 13 and 80 <= T <= 112:
            HI -= ((13 - rh) * 0.25) * math.sqrt((17 - abs(T - 95)) * 0.05882)
        elif rh > 85 and 80 <= T <= 87:
            HI += ((rh - 85) * 0.1) * ((87 - T) * 0.2)

    return cast(float, round(TC.convert(HI, UnitOfTemperature.FAHRENHEIT, temp_unit), 2))


def compute_absolute_humidity(temp: float, rh: float, temp_unit: str) -> float:
    """Calculate absolute humidity from temperature and humidity.

    https://carnotcycle.wordpress.com/2012/08/04/how-to-convert-relative-humidity-to-absolute-humidity
    """
    Tc = TC.convert(temp, temp_unit, UnitOfTemperature.CELSIUS)
    abs_humidity = (6.112 * math.exp((17.67 * Tc) / (243.5 + Tc)) * rh * 2.1674) / (Tc + 273.15)
    return round(abs_humidity, 2)  # type: ignore


def compute_frost_point(temp: float, rh: float, temp_unit: str) -> float:
    """Calculate frost point from temperature and humidity.

    https://pon.fr/dzvents-alerte-givre-et-calcul-humidite-absolue
    """
    dp = compute_dew_point(temp, rh, temp_unit)
    T = TC.convert(temp, temp_unit, UnitOfTemperature.KELVIN)
    Td = TC.convert(dp, temp_unit, UnitOfTemperature.KELVIN)

    frostpoint = (Td + (2671.02 / ((2954.61 / T) + 2.193665 * math.log(T) - 13.3448)) - T) - 273.15

    return cast(float, round(TC.convert(frostpoint, UnitOfTemperature.CELSIUS, temp_unit), 2))


def compute_frost_risk(temp: float, rh: float, temp_unit: str) -> FrostRisk:
    """Calculate frost risk from temperature and humidity."""
    abshum = compute_absolute_humidity(temp, rh, temp_unit)
    frostpoint = compute_frost_point(temp, rh, temp_unit)

    temp_c = TC.convert(temp, temp_unit, UnitOfTemperature.CELSIUS)
    frostpoint_c = TC.convert(frostpoint, temp_unit, UnitOfTemperature.CELSIUS)

    abs_humidity_threshold = 2.8
    if temp_c <= 1 and frostpoint_c <= 0:
        return FrostRisk.UNLIKELY if abshum <= abs_humidity_threshold else FrostRisk.HIGHLY_PROBABLE

    return (
        FrostRisk.PROBABLE
        if temp_c <= 4 and frostpoint_c <= 0.5 and abshum > abs_humidity_threshold
        else FrostRisk.NO_RISK
    )


def compute_simmer_index(temp: float, rh: float, temp_unit: str) -> float:
    """Calculate summer simmer index from temperature and humidity.

    https://www.vcalc.com/wiki/rklarsen/Summer+Simmer+Index
    """
    Tf = TC.convert(temp, temp_unit, UnitOfTemperature.FAHRENHEIT)
    ssi = 1.98 * (Tf - (0.55 - (0.0055 * rh)) * (Tf - 58)) - 56.83
    return cast(float, round(TC.convert(ssi, UnitOfTemperature.FAHRENHEIT, temp_unit), 2))


def compute_moist_air_enthalpy(temp: float, rh: float, temp_unit: str) -> float:
    """Calculate moist air enthalpy (kJ/kg) from temperature and humidity."""

    tc = TC.convert(temp, temp_unit, UnitOfTemperature.CELSIUS)
    tk = TC.convert(tc, UnitOfTemperature.CELSIUS, UnitOfTemperature.KELVIN)

    # calculate saturation vapour pressure for temperature
    if tc < 0:
        vp_saturation = math.exp(
            -5674.5359 / tk
            + 6.3925247
            + tk
            * (-0.9677843e-2 + tk * (0.62215701e-6 + tk * (0.20747825e-8 + -0.9484024e-12 * tk)))
            + 4.1635019 * math.log(tk)
        )
    else:
        vp_saturation = math.exp(
            -5800.2206 / tk
            + 1.3914993
            + tk * (-0.048640239 + tk * (0.41764768e-4 + tk * -0.14452093e-7))
            + 6.5459673 * math.log(tk)
        )

    vp = rh / 100 * vp_saturation
    hum_ratio = 0.62198 * vp / (101325 - vp)

    enthalpy_dry_air = 1004 * tc
    enthalpy_sat_vap = 2501000 + 1805 * tc
    enthalpy = enthalpy_dry_air + hum_ratio * enthalpy_sat_vap

    return cast(float, round(enthalpy / 1000, 2))
