"""TODO."""
from __future__ import annotations

from datetime import datetime
import logging
from typing import Any, Callable, Coroutine, Final, ParamSpec, TypeVar, cast

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

_LOGGER = logging.getLogger(__name__)

REQUIREMENTS: Final = ["pytomorrowio>=0.3.1"]
DESCRIPTION: Final = "To get an API key, sign up at [Tomorrow.io](https://app.tomorrow.io/signup)."
SCHEMA: Final = vol.Schema(
    {
        vol.Required("api_key"): str,
        vol.Required("location"): selector({"location": {"radius": False}}),
    }
)


TMRW_ATTR_TIMESTAMP = "startTime"
TMRW_ATTR_TEMPERATURE = "temperature"
TMRW_ATTR_HUMIDITY = "humidity"
TMRW_ATTR_WIND_SPEED = "windSpeed"
TMRW_ATTR_POLLEN_TREE = "treeIndex"
TMRW_ATTR_POLLEN_WEED = "weedIndex"
TMRW_ATTR_POLLEN_GRASS = "grassIndex"

FIELDS = [
    TMRW_ATTR_TEMPERATURE,
    TMRW_ATTR_HUMIDITY,
    TMRW_ATTR_WIND_SPEED,
    TMRW_ATTR_POLLEN_GRASS,
    TMRW_ATTR_POLLEN_TREE,
    TMRW_ATTR_POLLEN_WEED,
]


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
        super().__init__(**kwargs)
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
    def _to_weather_data(date_time: datetime, values: dict[str, Any]) -> WeatherData:
        return WeatherData(
            date_time=date_time,
            temp=values[TMRW_ATTR_TEMPERATURE],
            humidity=values[TMRW_ATTR_HUMIDITY],
            wind_speed=values[TMRW_ATTR_WIND_SPEED],
            pollen=max(
                values.get(TMRW_ATTR_POLLEN_TREE, 0),
                values.get(TMRW_ATTR_POLLEN_WEED, 0),
                values.get(TMRW_ATTR_POLLEN_GRASS, 0),
            ),
        )

    @async_exception_handler
    async def realtime(self) -> WeatherData:
        """Retrieve realtime weather from pytomorrowio."""
        realtime = await self._api.realtime(FIELDS)
        return self._to_weather_data(utcnow().replace(microsecond=0), realtime)

    @async_exception_handler
    async def forecast(self) -> list[WeatherData]:
        """Retrieve weather forecast from pytomorrowio."""
        hourly_forecast = await self._api.forecast_hourly(FIELDS, start_time=utcnow())

        result: list[WeatherData] = []
        for forecast in hourly_forecast:
            start_time = parse_datetime(forecast.get(TMRW_ATTR_TIMESTAMP))
            values = forecast.get("values")
            if not start_time or not values:
                break
            result.append(self._to_weather_data(start_time, values))
        return result
