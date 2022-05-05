"""TODO."""
from __future__ import annotations

import logging
import sys
from typing import Any, Callable, Coroutine, Final, Mapping, Sequence, TypeVar, cast

from homeassistant.const import (
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LOCATION,
    CONF_LONGITUDE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import selector
from homeassistant.util.dt import parse_datetime, utcnow
from pytomorrowio import TomorrowioV4, __version__ as PYTOMORROWIO_VERSION
from pytomorrowio.exceptions import (
    CantConnectException,
    InvalidAPIKeyException,
    RateLimitedException,
)
import voluptuous as vol

from .provider import PROVIDERS, Provider, ProviderError, WeatherData
from .schemas import value_or_default

if sys.version_info >= (3, 10):
    from typing import ParamSpec
else:
    from typing_extensions import ParamSpec


_LOGGER = logging.getLogger(__name__)

REQUIREMENTS: Final = ["pytomorrowio>=0.3.1"]
DESCRIPTION: Final = "To get an API key, sign up at [Tomorrow.io](https://app.tomorrow.io/signup)."

FIELDS = ["temperature", "humidity", "windSpeed", "treeIndex", "weedIndex", "grassIndex"]

_ParamT = ParamSpec("_ParamT")
_ResultT = TypeVar("_ResultT")


def async_exception_handler(
    wrapped: Callable[_ParamT, Coroutine[Any, Any, _ResultT]]
) -> Callable[_ParamT, Coroutine[Any, Any, _ResultT]]:
    """`pytomorrowio` exception handler."""

    async def wrapper(*args: _ParamT.args, **kwargs: _ParamT.kwargs) -> _ResultT:
        try:
            return await wrapped(*args, **kwargs)
        except InvalidAPIKeyException as exc:
            raise ProviderError("invalid_api_key") from exc
        except RateLimitedException as exc:
            raise ProviderError("rate_limited") from exc
        except CantConnectException as exc:
            raise ProviderError("cannot_connect") from exc
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.exception("%s from pytomorrowio", type(exc), exc_info=exc)
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


@PROVIDERS.register("tomorrowio")
class TomorrowioWeatherProvider(Provider):
    """Tomorrow.io weather provider."""

    def __init__(
        self,
        hass: HomeAssistant,
        /,
        api_key: str,
        location: Mapping[str, float],
    ) -> None:
        """Initialize provider."""
        super().__init__(hass)
        latitude = float(location["latitude"])
        longitude = float(location["longitude"])

        unit_system = "metric" if hass.config.units.is_metric else "imperial"
        session = async_get_clientsession(hass)
        self._api = TomorrowioV4(
            apikey=api_key,
            latitude=latitude,
            longitude=longitude,
            unit_system=unit_system,
            session=session,
        )

    @property
    def attribution(self) -> str:
        """Return attribution."""
        return "Weather data provided by Tomorrow.io"

    @property
    def version(self) -> str:
        """Return dependency version."""
        return cast(str, PYTOMORROWIO_VERSION)

    @staticmethod
    def _to_weather_data(
        startTime: str,
        /,
        temperature: float,
        humidity: float,
        windSpeed: float,
        treeIndex: int = 0,
        weedIndex: int = 0,
        grassIndex: int = 0,
    ) -> WeatherData:
        return WeatherData(
            date_time=parse_datetime(startTime),
            temp=temperature,
            humidity=humidity,
            wind_speed=windSpeed,
            pollen=max(treeIndex, weedIndex, grassIndex),
        )

    @async_exception_handler
    async def fetch_realtime(self) -> WeatherData | None:
        """Retrieve realtime weather from pytomorrowio."""
        realtime = await self._api.realtime(FIELDS)
        start_time = utcnow().replace(microsecond=0).isoformat()
        return self._to_weather_data(start_time, **realtime)

    @async_exception_handler
    async def fetch_forecast(self) -> Sequence[WeatherData] | None:
        """Retrieve weather forecast from pytomorrowio."""
        hourly_forecast = await self._api.forecast_hourly(FIELDS, start_time=utcnow())
        return [
            self._to_weather_data(interval["startTime"], **interval["values"])
            for interval in hourly_forecast
        ]
