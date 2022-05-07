"""This is a work in progress until HA bumps pynws to 1.4.1+."""
from __future__ import annotations

import logging
import sys
from typing import Any, Callable, Coroutine, Final, Mapping, Sequence, TypeVar, cast

from aiohttp import ClientError
from homeassistant.const import (
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LOCATION,
    CONF_LONGITUDE,
    SPEED_KILOMETERS_PER_HOUR,
    TEMP_CELSIUS,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util.dt import parse_datetime, utcnow
from homeassistant.util.speed import convert as convert_speed
from homeassistant.util.temperature import convert as convert_temp
from pynws import SimpleNWS
from pynws import version as PYNWS_VERSION
from pynws.const import Detail

from .provider import PROVIDERS, Provider, ProviderError, WeatherData

if sys.version_info >= (3, 10):
    from typing import ParamSpec
else:
    from typing_extensions import ParamSpec


_LOGGER = logging.getLogger(__name__)

REQUIREMENTS: Final = ["pynws>=1.4.1"]
DESCRIPTION: Final = "For now, an API Key can be anything. It is recommended to use a valid email address.\n\nThe National Weather Service does not provide pollen data."

_ParamT = ParamSpec("_ParamT")
_ResultT = TypeVar("_ResultT")


def _async_exception_handler(
    wrapped: Callable[_ParamT, Coroutine[Any, Any, _ResultT]]
) -> Callable[_ParamT, Coroutine[Any, Any, _ResultT]]:
    """`pynws` exception handler."""

    async def wrapper(*args: _ParamT.args, **kwargs: _ParamT.kwargs) -> _ResultT:
        try:
            return await wrapped(*args, **kwargs)
        except ClientError as exc:
            _LOGGER.exception("%s from pynws", type(exc), exc_info=exc)
            raise ProviderError("cannot_connect") from exc
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.exception("%s from pynws", type(exc), exc_info=exc)
            raise ProviderError("unknown") from exc

    return wrapper


@PROVIDERS.register("nws")
class NwsWeatherProvider(Provider):
    """National Weather Service weather provider."""

    def __init__(self, hass: HomeAssistant, config: Mapping[str, Any]) -> None:
        """Initialize provider."""
        super().__init__(hass)
        self._temp_unit = hass.config.units.temperature_unit
        self._speed_unit = hass.config.units.wind_speed_unit
        location = config[CONF_LOCATION]
        self._api = SimpleNWS(
            location[CONF_LATITUDE],
            location[CONF_LONGITUDE],
            config[CONF_API_KEY],
            async_get_clientsession(hass),
        )

    @property
    def attribution(self) -> str:
        """Return attribution."""
        return "Weather data provided by the National Weather Service/NOAA"

    @property
    def version(self) -> str:
        """Return dependency version."""
        return cast(str, PYNWS_VERSION)

    def _to_weather_data(self, **kwargs: Any) -> WeatherData | None:
        start_time: str = kwargs.pop(Detail.START_TIME)
        temperature: float | None = kwargs.pop(Detail.TEMPERATURE, None)
        humidity: float | None = kwargs.pop(Detail.RELATIVE_HUMIDITY, None)
        wind_speed: float | None = kwargs.pop(Detail.WIND_SPEED, None)
        if temperature is None or humidity is None or wind_speed is None:
            return None

        return WeatherData(
            date_time=parse_datetime(start_time),
            temp=convert_temp(temperature, TEMP_CELSIUS, self._temp_unit),
            humidity=humidity,
            wind_speed=convert_speed(wind_speed, SPEED_KILOMETERS_PER_HOUR, self._speed_unit),
            pollen=None,
        )

    @_async_exception_handler
    async def fetch_realtime(self) -> WeatherData | None:
        """Retrieve realtime weather from pynws."""
        if not self._api.station:
            await self._api.set_station()
        await self._api.update_observation(limit=1)
        obs = self._api.observation
        return self._to_weather_data(startTime=utcnow().replace(microsecond=0).isoformat(), **obs)

    @_async_exception_handler
    async def fetch_forecast(self) -> Sequence[WeatherData] | None:
        """Retrieve weather forecast from pynws."""
        if not self._api.station:
            await self._api.set_station()
        await self._api.update_detailed_forecast()
        forecast = self._api.detailed_forecast
        hourly_forecast = forecast.get_details_by_hour(start_time=utcnow(), hours=168)
        results = []
        for interval in hourly_forecast:
            result = self._to_weather_data(**interval)
            assert result is not None
            results.append(result)
        return results
