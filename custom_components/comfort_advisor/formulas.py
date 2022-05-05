"""Weather formulas."""
from __future__ import annotations

from enum import IntEnum
import math
from typing import cast

from homeassistant.const import TEMP_CELSIUS, TEMP_FAHRENHEIT, TEMP_KELVIN
from homeassistant.util.temperature import convert as convert_temp


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
    T = convert_temp(temp, temp_unit, TEMP_CELSIUS)
    b, c = 17.67, 243.5
    gamma = math.log(rh / 100) + b * T / (c + T)
    Td = c * gamma / (b - gamma)
    return cast(float, round(convert_temp(Td, TEMP_CELSIUS, temp_unit), 2))


def compute_heat_index(temp: float, rh: float, temp_unit: str) -> float:
    """Calculate heat index from temperature and humidity.

    http://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml
    """
    T = convert_temp(temp, temp_unit, TEMP_FAHRENHEIT)
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

    return cast(float, round(convert_temp(HI, TEMP_FAHRENHEIT, temp_unit), 2))


def compute_absolute_humidity(temp: float, rh: float, temp_unit: str) -> float:
    """Calculate absolute humidity from temperature and humidity.

    https://carnotcycle.wordpress.com/2012/08/04/how-to-convert-relative-humidity-to-absolute-humidity
    """
    Tc = convert_temp(temp, temp_unit, TEMP_CELSIUS)
    abs_humidity = (6.112 * math.exp((17.67 * Tc) / (243.5 + Tc)) * rh * 2.1674) / (Tc + 273.15)
    return round(abs_humidity, 2)  # type: ignore


def compute_frost_point(temp: float, rh: float, temp_unit: str) -> float:
    """Calculate frost point from temperature and humidity.

    https://pon.fr/dzvents-alerte-givre-et-calcul-humidite-absolue
    """
    dp = compute_dew_point(temp, rh, temp_unit)
    T = convert_temp(temp, temp_unit, TEMP_KELVIN)
    Td = convert_temp(dp, temp_unit, TEMP_KELVIN)

    frostpoint = (Td + (2671.02 / ((2954.61 / T) + 2.193665 * math.log(T) - 13.3448)) - T) - 273.15

    return cast(float, round(convert_temp(frostpoint, TEMP_CELSIUS, temp_unit), 2))


def compute_frost_risk(temp: float, rh: float, temp_unit: str) -> FrostRisk:
    """Calculate frost risk from temperature and humidity."""
    abshum = compute_absolute_humidity(temp, rh, temp_unit)
    frostpoint = compute_frost_point(temp, rh, temp_unit)

    temp_c = convert_temp(temp, temp_unit, TEMP_CELSIUS)
    frostpoint_c = convert_temp(frostpoint, temp_unit, TEMP_CELSIUS)

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
    Tf = convert_temp(temp, temp_unit, TEMP_FAHRENHEIT)
    ssi = 1.98 * (Tf - (0.55 - (0.0055 * rh)) * (Tf - 58)) - 56.83
    return cast(float, round(convert_temp(ssi, TEMP_FAHRENHEIT, temp_unit), 2))
