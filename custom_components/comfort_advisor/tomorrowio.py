"""TODO."""
from __future__ import annotations

from datetime import datetime
import logging
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Final, cast

from homeassistant.const import CONF_LATITUDE, CONF_LOCATION, CONF_LONGITUDE, CONF_API_KEY
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

_LOGGER = logging.getLogger(__name__)

REQUIREMENTS: Final = ["pytomorrowio>=0.3.1"]
DESCRIPTION: Final = "To get an API key, sign up at [Tomorrow.io](https://app.tomorrow.io/signup)."

FIELDS = ["temperature", "humidity", "windSpeed", "treeIndex", "weedIndex", "grassIndex"]


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


if TYPE_CHECKING:
    from typing import ParamSpec, TypeVar

    _ParamT = ParamSpec("_ParamT")  # the callable parameters
    _ResultT = TypeVar("_ResultT")  # the callable/awaitable return type


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
        except Exception as exc:
            _LOGGER.exception("Error from pytomorrowio: %s", exc_info=exc)
            raise ProviderError("unknown") from exc

    return wrapper


@PROVIDERS.register("tomorrowio")
class TomorrowioWeatherProvider(Provider):
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
        return "Weather forecast provided by Tomorrow.io"

    @property
    def version(self) -> str:
        """Return dependency version."""
        return cast(str, PYTOMORROWIO_VERSION)

    @staticmethod
    def _to_weather_data(  # type: ignore
        date_time: datetime,
        *,
        temperature: float,
        humidity: float,
        windSpeed: float,
        treeIndex: int = 0,
        weedIndex: int = 0,
        grassIndex: int = 0,
        **kwargs,
    ) -> WeatherData:
        return WeatherData(
            date_time=date_time,
            temp=temperature,
            humidity=humidity,
            wind_speed=windSpeed,
            pollen=max(treeIndex, weedIndex, grassIndex),
        )

    @async_exception_handler
    async def realtime(self) -> WeatherData:
        """Retrieve realtime weather from pytomorrowio."""
        realtime = await self._api.realtime(FIELDS)
        return self._to_weather_data(utcnow().replace(microsecond=0), **realtime)

    @async_exception_handler
    async def forecast(self) -> list[WeatherData]:
        """Retrieve weather forecast from pytomorrowio."""
        hourly_forecast = await self._api.forecast_hourly(FIELDS, start_time=utcnow())
        result: list[WeatherData] = []
        for interval in hourly_forecast:
            start_time = parse_datetime(interval.get("startTime"))
            result.append(self._to_weather_data(start_time, **interval["values"]))
        return result
