"""TODO."""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Final

from homeassistant.const import SPEED_MILES_PER_HOUR, TEMP_FAHRENHEIT
from homeassistant.core import HomeAssistant
from homeassistant.util.dt import utcnow
import voluptuous as vol

from .weather import WEATHER_PROVIDERS, WeatherData, WeatherProvider

REQUIREMENTS: list[str] = []
DESCRIPTION: Final = "Faking it since 1982"
SCHEMA = vol.Schema({}, extra=vol.PREVENT_EXTRA)


@WEATHER_PROVIDERS.register("fake")
class FakeWeatherProvider(WeatherProvider):
    """TODO."""

    def __init__(self, hass: HomeAssistant, **kwargs):
        """TODO."""
        super().__init__(**kwargs)
        self._units = hass.config.units

    def _to_native_units(self, data: dict[str, Any]) -> WeatherData:
        return WeatherData(
            date_time=data["date_time"],
            temp=self._units.temperature(data["temp"], TEMP_FAHRENHEIT),
            humidity=data["humidity"],
            wind_speed=self._units.wind_speed(data["wind_speed"], SPEED_MILES_PER_HOUR),
            pollen=data["pollen"],
        )

    @property
    def attribution(self) -> str:
        """Return attribution to use in UI."""
        return "Fake it 'til you make it."

    @property
    def version(self) -> str:
        """Return attribution to use in UI."""
        return "0.0.0"

    async def realtime(self) -> WeatherData:
        """TODO."""
        results = {
            "date_time": utcnow().replace(microsecond=0),
            "temp": 84.2,
            "humidity": 49,
            "wind_speed": 7.13,
            "pollen": 1,
        }
        return self._to_native_units(results)

    async def forecast(self) -> list[WeatherData]:
        """TODO."""
        start_time = utcnow().replace(minute=0, second=0, microsecond=0)
        results = [
            {
                "date_time": start_time,
                "temp": 82.96,
                "humidity": 53,
                "wind_speed": 7.83,
                "pollen": 1,
            },
            {
                "date_time": start_time + timedelta(hours=1),
                "temp": 84.72,
                "humidity": 49.41,
                "wind_speed": 5.35,
                "pollen": 1,
            },
            {
                "date_time": start_time + timedelta(hours=2),
                "temp": 87.15,
                "humidity": 42.68,
                "wind_speed": 5.6,
                "pollen": 2,
            },
            {
                "date_time": start_time + timedelta(hours=3),
                "temp": 89.32,
                "humidity": 36.22,
                "wind_speed": 5.85,
                "pollen": 3,
            },
            {
                "date_time": start_time + timedelta(hours=4),
                "temp": 87.24,
                "humidity": 49.4,
                "wind_speed": 8.47,
                "pollen": 2,
            },
            {
                "date_time": start_time + timedelta(hours=5),
                "temp": 85.39,
                "humidity": 54.07,
                "wind_speed": 10.03,
                "pollen": 1,
            },
            {
                "date_time": start_time + timedelta(hours=6),
                "temp": 83.37,
                "humidity": 55.87,
                "wind_speed": 11.2,
                "pollen": 1,
            },
            {
                "date_time": start_time + timedelta(hours=7),
                "temp": 82.33,
                "humidity": 56.44,
                "wind_speed": 9.13,
                "pollen": 1,
            },
            {
                "date_time": start_time + timedelta(hours=8),
                "temp": 78.8,
                "humidity": 63.39,
                "wind_speed": 8.78,
                "pollen": 2,
            },
            {
                "date_time": start_time + timedelta(hours=9),
                "temp": 77.31,
                "humidity": 64.85,
                "wind_speed": 5.79,
                "pollen": 1,
            },
            {
                "date_time": start_time + timedelta(hours=10),
                "temp": 76.05,
                "humidity": 72.93,
                "wind_speed": 6.26,
                "pollen": 1,
            },
            {
                "date_time": start_time + timedelta(hours=11),
                "temp": 75.87,
                "humidity": 74.46,
                "wind_speed": 2.19,
                "pollen": 1,
            },
            {
                "date_time": start_time + timedelta(hours=12),
                "temp": 74.55,
                "humidity": 81.54,
                "wind_speed": 1.94,
                "pollen": 1,
            },
            {
                "date_time": start_time + timedelta(hours=13),
                "temp": 74.56,
                "humidity": 82.14,
                "wind_speed": 1.19,
                "pollen": 1,
            },
            {
                "date_time": start_time + timedelta(hours=14),
                "temp": 74.07,
                "humidity": 83.85,
                "wind_speed": 2.32,
                "pollen": 1,
            },
            {
                "date_time": start_time + timedelta(hours=15),
                "temp": 73.51,
                "humidity": 82.5,
                "wind_speed": 4.74,
                "pollen": 1,
            },
            {
                "date_time": start_time + timedelta(hours=16),
                "temp": 71.11,
                "humidity": 85.46,
                "wind_speed": 4.61,
                "pollen": 1,
            },
            {
                "date_time": start_time + timedelta(hours=17),
                "temp": 72.23,
                "humidity": 91.41,
                "wind_speed": 1.45,
                "pollen": 2,
            },
            {
                "date_time": start_time + timedelta(hours=18),
                "temp": 71.53,
                "humidity": 91.41,
                "wind_speed": 2.14,
                "pollen": 2,
            },
            {
                "date_time": start_time + timedelta(hours=19),
                "temp": 68.35,
                "humidity": 90.56,
                "wind_speed": 4.15,
                "pollen": 2,
            },
            {
                "date_time": start_time + timedelta(hours=20),
                "temp": 67.75,
                "humidity": 92.87,
                "wind_speed": 3.98,
                "pollen": 2,
            },
            {
                "date_time": start_time + timedelta(hours=21),
                "temp": 70.8,
                "humidity": 86.02,
                "wind_speed": 5.41,
                "pollen": 1,
            },
            {
                "date_time": start_time + timedelta(hours=22),
                "temp": 75.47,
                "humidity": 70.83,
                "wind_speed": 6.22,
                "pollen": 1,
            },
            {
                "date_time": start_time + timedelta(hours=23),
                "temp": 79.16,
                "humidity": 60.35,
                "wind_speed": 7.51,
                "pollen": 1,
            },
            {
                "date_time": start_time + timedelta(hours=24),
                "temp": 82.59,
                "humidity": 51.27,
                "wind_speed": 6.03,
                "pollen": 1,
            },
            {
                "date_time": start_time + timedelta(hours=25),
                "temp": 85.86,
                "humidity": 43.15,
                "wind_speed": 4.65,
                "pollen": 2,
            },
            {
                "date_time": start_time + timedelta(hours=26),
                "temp": 88.7,
                "humidity": 37.39,
                "wind_speed": 2.34,
                "pollen": 3,
            },
            {
                "date_time": start_time + timedelta(hours=27),
                "temp": 88.86,
                "humidity": 37.04,
                "wind_speed": 2.98,
                "pollen": 2,
            },
            {
                "date_time": start_time + timedelta(hours=28),
                "temp": 85.66,
                "humidity": 47.24,
                "wind_speed": 11.04,
                "pollen": 2,
            },
            {
                "date_time": start_time + timedelta(hours=29),
                "temp": 83.27,
                "humidity": 55.13,
                "wind_speed": 10.52,
                "pollen": 3,
            },
            {
                "date_time": start_time + timedelta(hours=30),
                "temp": 82.66,
                "humidity": 53.13,
                "wind_speed": 12.41,
                "pollen": 1,
            },
            {
                "date_time": start_time + timedelta(hours=31),
                "temp": 81.21,
                "humidity": 55.83,
                "wind_speed": 11.9,
                "pollen": 1,
            },
            {
                "date_time": start_time + timedelta(hours=32),
                "temp": 79.58,
                "humidity": 61.12,
                "wind_speed": 11.89,
                "pollen": 1,
            },
            {
                "date_time": start_time + timedelta(hours=33),
                "temp": 77.13,
                "humidity": 70.73,
                "wind_speed": 10.05,
                "pollen": 1,
            },
            {
                "date_time": start_time + timedelta(hours=34),
                "temp": 75.84,
                "humidity": 76.31,
                "wind_speed": 6.49,
                "pollen": 1,
            },
            {
                "date_time": start_time + timedelta(hours=35),
                "temp": 74.84,
                "humidity": 81.41,
                "wind_speed": 3.51,
                "pollen": 1,
            },
            {
                "date_time": start_time + timedelta(hours=36),
                "temp": 74.17,
                "humidity": 85.38,
                "wind_speed": 4.29,
                "pollen": 1,
            },
            {
                "date_time": start_time + timedelta(hours=37),
                "temp": 73.54,
                "humidity": 87.68,
                "wind_speed": 5.05,
                "pollen": 1,
            },
            {
                "date_time": start_time + timedelta(hours=38),
                "temp": 72.84,
                "humidity": 87.64,
                "wind_speed": 4.74,
                "pollen": 1,
            },
            {
                "date_time": start_time + timedelta(hours=39),
                "temp": 71.56,
                "humidity": 89.64,
                "wind_speed": 3.45,
                "pollen": 1,
            },
            {
                "date_time": start_time + timedelta(hours=40),
                "temp": 70.72,
                "humidity": 91.53,
                "wind_speed": 3.68,
                "pollen": 1,
            },
            {
                "date_time": start_time + timedelta(hours=41),
                "temp": 69.72,
                "humidity": 93.65,
                "wind_speed": 3.62,
                "pollen": 0,
            },
            {
                "date_time": start_time + timedelta(hours=42),
                "temp": 69.85,
                "humidity": 92.57,
                "wind_speed": 3.62,
                "pollen": 0,
            },
            {
                "date_time": start_time + timedelta(hours=43),
                "temp": 71.81,
                "humidity": 88.79,
                "wind_speed": 1.76,
                "pollen": 0,
            },
            {
                "date_time": start_time + timedelta(hours=44),
                "temp": 71.71,
                "humidity": 89.82,
                "wind_speed": 1.16,
                "pollen": 0,
            },
            {
                "date_time": start_time + timedelta(hours=45),
                "temp": 72.53,
                "humidity": 88.48,
                "wind_speed": 2.1,
                "pollen": 0,
            },
            {
                "date_time": start_time + timedelta(hours=46),
                "temp": 76.18,
                "humidity": 73.72,
                "wind_speed": 3.84,
                "pollen": 0,
            },
            {
                "date_time": start_time + timedelta(hours=47),
                "temp": 79.08,
                "humidity": 64,
                "wind_speed": 4.1,
                "pollen": 1,
            },
        ]
        return [self._to_native_units(data) for data in results]
