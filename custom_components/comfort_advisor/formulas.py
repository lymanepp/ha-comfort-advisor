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
    Tc = TC.convert(temp, temp_unit, UnitOfTemperature.CELSIUS)
    A0 = 373.15 / (273.15 + Tc)
    SUM = -7.90298 * (A0 - 1)
    SUM += 5.02808 * math.log(A0, 10)
    SUM += -1.3816e-7 * (pow(10, (11.344 * (1 - 1 / A0))) - 1)
    SUM += 8.1328e-3 * (pow(10, (-3.49149 * (A0 - 1))) - 1)
    SUM += math.log(1013.246, 10)
    VP = pow(10, SUM - 3) * rh
    Td = math.log(VP / 0.61078)
    Td = (241.88 * Td) / (17.558 - Td)
    return cast(float, round(TC.convert(Td, UnitOfTemperature.CELSIUS, temp_unit), 2))


def compute_heat_index(temp: float, rh: float, temp_unit: str) -> float:
    """Calculate heat index from temperature and humidity.

    http://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml
    """
    Tc = TC.convert(temp, temp_unit, UnitOfTemperature.FAHRENHEIT)
    HI = 0.5 * (Tc + 61.0 + ((Tc - 68.0) * 1.2) + (rh * 0.094))
    if ((Tc + HI) / 2) >= 80:
        HI = (
            -42.379
            + (2.04901523 * Tc)
            + (10.14333127 * rh)
            + (-0.22475541 * Tc * rh)
            + (-0.00683783 * Tc * Tc)
            + (-0.05481717 * rh * rh)
            + (0.00122874 * Tc * Tc * rh)
            + (0.00085282 * Tc * rh * rh)
            + (-0.00000199 * Tc * Tc * rh * rh)
        )
        if rh < 13 and 80 <= Tc <= 112:
            HI -= ((13 - rh) * 0.25) * math.sqrt((17 - abs(Tc - 95)) * 0.05882)
        elif rh > 85 and 80 <= Tc <= 87:
            HI += ((rh - 85) * 0.1) * ((87 - Tc) * 0.2)

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
    Tk = TC.convert(temp, temp_unit, UnitOfTemperature.KELVIN)
    Td = TC.convert(dp, temp_unit, UnitOfTemperature.KELVIN)

    frostpoint = (Td + (2671.02 / ((2954.61 / Tk) + 2.193665 * math.log(Tk) - 13.3448)) - Tk) - 273.15

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

    Tc = TC.convert(temp, temp_unit, UnitOfTemperature.CELSIUS)
    Tk = TC.convert(Tc, UnitOfTemperature.CELSIUS, UnitOfTemperature.KELVIN)

    # calculate saturation vapour pressure for temperature
    if Tc < 0:
        vp_saturation = math.exp(
            -5674.5359 / Tk
            + 6.3925247
            + Tk
            * (-0.9677843e-2 + Tk * (0.62215701e-6 + Tk * (0.20747825e-8 + -0.9484024e-12 * Tk)))
            + 4.1635019 * math.log(Tk)
        )
    else:
        vp_saturation = math.exp(
            -5800.2206 / Tk
            + 1.3914993
            + Tk * (-0.048640239 + Tk * (0.41764768e-4 + Tk * -0.14452093e-7))
            + 6.5459673 * math.log(Tk)
        )

    vp = rh / 100 * vp_saturation
    hum_ratio = 0.62198 * vp / (101325 - vp)

    enthalpy_dry_air = 1004 * Tc
    enthalpy_sat_vap = 2501000 + 1805 * Tc
    enthalpy = enthalpy_dry_air + hum_ratio * enthalpy_sat_vap

    return cast(float, round(enthalpy / 1000, 2))
