"""This is a work in progress until HA bumps pynws to 1.4.1+."""
from __future__ import annotations

from functools import wraps
from typing import (
    Any,
    Callable,
    Coroutine,
    Mapping,
    ParamSpec,
    Sequence,
    SupportsFloat,
    TypeVar,
    cast,
)

from aiohttp import ClientError, ClientResponseError
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
from homeassistant.util.unit_conversion import SpeedConverter as SC
from homeassistant.util.unit_conversion import TemperatureConverter as TC
from pynws import SimpleNWS
from pynws import version as PYNWS_VERSION
from pynws.const import Detail

from .provider import PROVIDERS, Provider, ProviderException, WeatherData, async_retry

_P = ParamSpec("_P")
_T = TypeVar("_T")


def async_handle_exceptions(
    wrapped: Callable[_P, Coroutine[Any, Any, _T]]
) -> Callable[_P, Coroutine[Any, Any, _T]]:
    """`pynws` exception handler."""

    @wraps(wrapped)
    async def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        try:
            return await wrapped(*args, **kwargs)
        except ClientResponseError as exc:
            raise ProviderException("api_error", can_retry=exc.status >= 500) from exc
        except ClientError as exc:
            raise ProviderException("cannot_connect", can_retry=True) from exc

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

    def _to_weather_data(self, values: Mapping[str, Any]) -> WeatherData:
        temp = values.get(Detail.TEMPERATURE)
        humidity = values.get(Detail.RELATIVE_HUMIDITY)
        wind_speed = values.get(Detail.WIND_SPEED)

        if not (  # NWS observation data is unreliable
            isinstance(temp, SupportsFloat)
            and isinstance(humidity, SupportsFloat)
            and isinstance(wind_speed, SupportsFloat)
        ):
            raise ProviderException("api_error")

        start_time = parse_datetime(values[Detail.START_TIME])
        temp = TC.convert(float(temp), TEMP_CELSIUS, self._temp_unit)
        humidity = float(humidity)
        wind_speed = SC.convert(float(wind_speed), SPEED_KILOMETERS_PER_HOUR, self._speed_unit)

        return WeatherData(start_time, temp, humidity, wind_speed, pollen=None)

    @async_retry
    @async_handle_exceptions
    async def fetch_realtime(self) -> WeatherData | None:
        """Retrieve realtime weather from pynws."""
        if not self._api.station:
            await self._api.set_station()
        await self._api.update_observation(limit=1)
        observation = self._api.observation
        observation[Detail.START_TIME] = utcnow().replace(microsecond=0).isoformat()
        return self._to_weather_data(observation)

    @async_retry
    @async_handle_exceptions
    async def fetch_forecast(self) -> Sequence[WeatherData] | None:
        """Retrieve weather forecast from pynws."""
        if not self._api.station:
            await self._api.set_station()
        await self._api.update_detailed_forecast()
        forecast = self._api.detailed_forecast
        hourly_forecast = forecast.get_details_by_hour(start_time=utcnow(), hours=168)
        return [self._to_weather_data(period) for period in hourly_forecast]
