"""Tomorrow.io data provider."""
from __future__ import annotations

import logging
import sys
from typing import Any, Callable, Coroutine, Final, Mapping, Sequence, TypeVar, cast

from homeassistant.const import CONF_API_KEY, CONF_LOCATION
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util.dt import parse_datetime, utcnow
from pytomorrowio import TomorrowioV4
from pytomorrowio import __version__ as PYTOMORROWIO_VERSION
from pytomorrowio.exceptions import (
    CantConnectException,
    InvalidAPIKeyException,
    RateLimitedException,
)

from .provider import PROVIDERS, Provider, ProviderError, WeatherData

if sys.version_info >= (3, 10):
    from typing import ParamSpec
else:
    from typing_extensions import ParamSpec


_LOGGER = logging.getLogger(__name__)

REQUIREMENTS: Final = ["pytomorrowio>=0.3.1"]
DESCRIPTION: Final = "To get an API key, sign up at [Tomorrow.io](https://app.tomorrow.io/signup)."

_FIELDS = ["temperature", "humidity", "windSpeed", "treeIndex", "weedIndex", "grassIndex"]

_ParamT = ParamSpec("_ParamT")
_ResultT = TypeVar("_ResultT")


def _async_exception_handler(
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


@PROVIDERS.register("tomorrowio")
class TomorrowioWeatherProvider(Provider):
    """Tomorrow.io weather provider."""

    def __init__(self, hass: HomeAssistant, config: Mapping[str, Any]) -> None:
        """Initialize provider."""
        super().__init__(hass)

        location = config[CONF_LOCATION]
        unit_system = "metric" if hass.config.units.is_metric else "imperial"

        self._api = TomorrowioV4(
            apikey=config[CONF_API_KEY],
            latitude=location["latitude"],
            longitude=location["longitude"],
            unit_system=unit_system,
            session=async_get_clientsession(hass),
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
    def _to_weather_data(startTime: str, values: Mapping[str, Any]) -> WeatherData:
        return WeatherData(
            date_time=parse_datetime(startTime),
            temp=float(values["temperature"]),
            humidity=float(values["humidity"]),
            wind_speed=float(values["windSpeed"]),
            pollen=max(values["treeIndex"], values["weedIndex"], values["grassIndex"]),
        )

    @_async_exception_handler
    async def fetch_realtime(self) -> WeatherData | None:
        """Retrieve realtime weather from pytomorrowio."""
        realtime = await self._api.realtime(_FIELDS)
        start_time = utcnow().replace(microsecond=0).isoformat()
        return self._to_weather_data(start_time, realtime)

    @_async_exception_handler
    async def fetch_forecast(self) -> Sequence[WeatherData] | None:
        """Retrieve weather forecast from pytomorrowio."""
        hourly_forecast = await self._api.forecast_hourly(_FIELDS, start_time=utcnow())
        return [
            self._to_weather_data(period["startTime"], period["values"])
            for period in hourly_forecast
        ]
