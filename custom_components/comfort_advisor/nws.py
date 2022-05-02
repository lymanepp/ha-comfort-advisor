"""This is a work in progress until HA bumps pynws to 1.4.1+."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from aiohttp import ClientConnectionError
from homeassistant.const import (
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LOCATION,
    CONF_LONGITUDE,
    TEMP_CELSIUS,
    SPEED_KILOMETERS_PER_HOUR,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import selector
from homeassistant.util.dt import parse_datetime, utcnow
from homeassistant.util.temperature import convert as convert_temp
from homeassistant.util.speed import convert as convert_speed
from pynws import SimpleNWS, version as PYNWS_VERSION
import voluptuous as vol

from .provider import PROVIDERS, Provider, ProviderError, WeatherData
from .schemas import value_or_default

if TYPE_CHECKING:
    from typing import Any, Callable, Coroutine, Final, ParamSpec, TypeVar

_LOGGER = logging.getLogger(__name__)

REQUIREMENTS: Final = ["pynws>=1.4.1"]
DESCRIPTION: Final = (
    "For now, an API Key can be anything. It is recommended to use a valid email address."
)


if TYPE_CHECKING:
    _ParamT = ParamSpec("_ParamT")  # the callable parameters
    _ResultT = TypeVar("_ResultT")  # the callable/awaitable return type


def async_exception_handler(
    wrapped: Callable[_ParamT, Coroutine[Any, Any, _ResultT]]
) -> Callable[_ParamT, Coroutine[Any, Any, _ResultT]]:
    """`pynws` exception handler."""

    async def wrapper(*args: _ParamT.args, **kwargs: _ParamT.kwargs) -> _ResultT:
        try:
            return await wrapped(*args, **kwargs)
        except ClientConnectionError as exc:
            raise ProviderError("cannot_connect") from exc
        except Exception as exc:
            _LOGGER.exception("Error from pynws: %s", exc_info=exc)
            raise ProviderError("unknown") from exc

    return wrapper


def build_schema(
    hass: HomeAssistant, *, api_key: str = vol.UNDEFINED, location: dict[str, float] = vol.UNDEFINED
) -> vol.Schema:
    """TODO."""
    default_location = {CONF_LATITUDE: hass.config.latitude, CONF_LONGITUDE: hass.config.longitude}
    return vol.Schema(
        {
            vol.Required(CONF_API_KEY, default=api_key): vol.All(str, vol.Length(min=1)),
            vol.Required(
                CONF_LOCATION, default=value_or_default(location, default_location)
            ): selector({"location": {"radius": False}}),
        }
    )


@PROVIDERS.register("nws")
class NwsWeatherProvider(Provider):
    """TODO."""

    def __init__(  # type: ignore
        self,
        hass: HomeAssistant,
        /,
        api_key: str,
        location: dict[str, float],
        **kwargs,
    ) -> None:
        """TODO."""
        self._temp_unit = hass.config.units.temperature_unit
        self._speed_unit = hass.config.units.wind_speed_unit

        latitude = float(location["latitude"])
        longitude = float(location["longitude"])

        session = async_get_clientsession(hass)

        self._api = SimpleNWS(latitude, longitude, api_key, session)

    @property
    def attribution(self) -> str:
        """Return attribution."""
        return "Forecast provided by the National Weather Service/NOAA"

    @property
    def version(self) -> str:
        """Return dependency version."""
        return cast(str, PYNWS_VERSION)

    def _to_weather_data(  # type: ignore
        self,
        *,
        startTime: str,
        temperature: float,
        relativeHumidity: float,
        windSpeed: float,
        **kwargs,
    ) -> WeatherData:
        return WeatherData(
            date_time=parse_datetime(startTime),
            temp=convert_temp(temperature, TEMP_CELSIUS, self._temp_unit),
            humidity=relativeHumidity,
            wind_speed=convert_speed(windSpeed, SPEED_KILOMETERS_PER_HOUR, self._speed_unit),
            pollen=None,
        )

    @async_exception_handler
    async def realtime(self) -> WeatherData:
        """TODO."""
        if not self._api.station:
            await self._api.set_station()
        await self._api.update_observation(limit=1)
        start_time = utcnow().replace(microsecond=0).isoformat()
        return self._to_weather_data(startTime=start_time, **(self._api.observation))

    @async_exception_handler
    async def forecast(self) -> list[WeatherData]:
        """TODO."""
        if not self._api.station:
            await self._api.set_station()
        await self._api.update_detailed_forecast()
        forecast = self._api.detailed_forecast
        hourly_forecast = forecast.get_details_by_hour(start_time=utcnow(), hours=24)
        return [self._to_weather_data(**interval) for interval in hourly_forecast]
