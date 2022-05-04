"""This is a work in progress until HA bumps pynws to 1.4.1+."""
from __future__ import annotations

import logging
from typing import (
    Any,
    Callable,
    Coroutine,
    Final,
    Mapping,
    ParamSpec,
    Sequence,
    TypeVar,
    cast,
)

from aiohttp import ClientConnectionError
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
from homeassistant.helpers.selector import selector
from homeassistant.util.dt import parse_datetime, utcnow
from homeassistant.util.speed import convert as convert_speed
from homeassistant.util.temperature import convert as convert_temp
from pynws import SimpleNWS, version as PYNWS_VERSION
from pynws.const import Detail
import voluptuous as vol

from .provider import PROVIDERS, Provider, ProviderError, WeatherData
from .schemas import value_or_default

_LOGGER = logging.getLogger(__name__)

REQUIREMENTS: Final = ["pynws>=1.4.1"]
DESCRIPTION: Final = "For now, an API Key can be anything. It is recommended to use a valid email address.\n\nThe National Weather Service API does not provide pollen data."

_ParamT = ParamSpec("_ParamT")
_ResultT = TypeVar("_ResultT")


def async_exception_handler(
    wrapped: Callable[_ParamT, Coroutine[Any, Any, _ResultT]]
) -> Callable[_ParamT, Coroutine[Any, Any, _ResultT]]:
    """`pynws` exception handler."""

    async def wrapper(*args: _ParamT.args, **kwargs: _ParamT.kwargs) -> _ResultT:
        try:
            return await wrapped(*args, **kwargs)
        except ClientConnectionError as exc:
            raise ProviderError("cannot_connect") from exc
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.exception("%s from pynws", type(exc), exc_info=exc)
            raise ProviderError("unknown") from exc

    return wrapper


def build_schema(
    hass: HomeAssistant,
    *,
    api_key: str = vol.UNDEFINED,
    location: Mapping[str, float] = vol.UNDEFINED,
) -> vol.Schema:
    """Build provider data schema."""
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
    """National Weather Service weather provider."""

    def __init__(
        self,
        hass: HomeAssistant,
        /,
        api_key: str,
        location: Mapping[str, float],
    ) -> None:
        """Initialize provider."""
        super().__init__(hass)
        self._temp_unit = hass.config.units.temperature_unit
        self._speed_unit = hass.config.units.wind_speed_unit

        self._api = SimpleNWS(
            location["latitude"], location["longitude"], api_key, async_get_clientsession(hass)
        )

    @property
    def attribution(self) -> str:
        """Return attribution."""
        return "Weather data provided by the National Weather Service/NOAA"

    @property
    def version(self) -> str:
        """Return dependency version."""
        return cast(str, PYNWS_VERSION)

    def _to_weather_data(
        self, *, start_time: str, temperature: float, humidity: float, wind_speed: float
    ) -> WeatherData | None:
        if start_time is None or temperature is None or humidity is None or wind_speed is None:
            return None
        return WeatherData(
            date_time=parse_datetime(start_time),
            temp=convert_temp(temperature, TEMP_CELSIUS, self._temp_unit),
            humidity=humidity,
            wind_speed=convert_speed(wind_speed, SPEED_KILOMETERS_PER_HOUR, self._speed_unit),
            pollen=None,
        )

    @async_exception_handler
    async def fetch_realtime(self) -> WeatherData | None:
        """Retrieve realtime weather from pynws."""
        if not self._api.station:
            await self._api.set_station()
        await self._api.update_observation(limit=1)
        obs = self._api.observation
        return self._to_weather_data(
            start_time=utcnow().replace(microsecond=0).isoformat(),
            temperature=obs.get("temperature"),
            humidity=obs.get("relativeHumidity"),
            wind_speed=obs.get("windSpeed"),
        )

    @async_exception_handler
    async def fetch_forecast(self) -> Sequence[WeatherData] | None:
        """Retrieve weather forecast from pynws."""
        if not self._api.station:
            await self._api.set_station()
        await self._api.update_detailed_forecast()
        forecast = self._api.detailed_forecast
        hourly_forecast = forecast.get_details_by_hour(start_time=utcnow(), hours=168)
        results = []
        for interval in hourly_forecast:
            result = self._to_weather_data(
                start_time=interval.get(Detail.START_TIME),
                temperature=interval.get(Detail.TEMPERATURE),
                humidity=interval.get(Detail.RELATIVE_HUMIDITY),
                wind_speed=interval.get(Detail.WIND_SPEED),
            )
            assert result is not None
            results.append(result)
        return results
