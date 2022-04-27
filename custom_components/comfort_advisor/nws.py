"""This is a work in progress until HA bumps pynws to 1.4.1+."""
from __future__ import annotations

from homeassistant.const import CONF_API_KEY, CONF_LOCATION
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import selector
from homeassistant.util.dt import parse_datetime, utcnow
from pynws import SimpleNWS, NwsError
from pynws.const import Detail
import voluptuous as vol

from .weather_provider import (
    WEATHER_PROVIDERS,
    WeatherData,
    WeatherProvider,
    WeatherProviderError,
)

REQUIREMENTS = ["pynws>=1.4.1"]

CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
        vol.Required(CONF_LOCATION): selector({"location": {"radius": False}}),
    },
    extra=vol.PREVENT_EXTRA,
)


def exception_handler(func):
    """Decorate TomorrowioV4 calls to handle exceptions."""

    async def handler(self, *args, **kwargs):
        try:
            await func(self, *args, **kwargs)
        except NwsError as exc:
            raise WeatherProviderError("api_error") from exc

    return handler


@WEATHER_PROVIDERS.register("nws")
class TomorrowioWeatherProvider(WeatherProvider):
    """TODO."""

    def __init__(self, hass: HomeAssistant, /, **kwargs) -> None:
        """TODO."""
        api_key: str = kwargs.pop("api_key")
        location = kwargs.pop("location")
        latitude = float(location["latitude"])
        longitude = float(location["longitude"])

        session = async_get_clientsession(hass)

        self._api = SimpleNWS(latitude, longitude, api_key, session)

    @exception_handler
    async def realtime(self) -> WeatherData:
        """TODO."""
        if not self._api.station:
            await self._api.set_station()
        await self._api.update_observation(limit=1)
        obs = self._api.observation
        # TODO: map to WeatherData
        # return self._to_weather_data(utcnow().replace(microsecond=0), realtime)

    @exception_handler
    async def forecast(self) -> list[WeatherData]:
        """TODO."""
        if not self._api.station:
            await self._api.set_station()
        await self._api.update_detailed_forecast()
        forecast = self._api.detailed_forecast
        now = utcnow()
        details_by_hour = forecast.get_details_by_hour(start_time=now, hours=24)
        result: list[WeatherData] = []
        for details in details_by_hour:
            start_time = parse_datetime(details[Detail.START_TIME])
            if start_time < now:
                continue
            result.append(
                WeatherData(
                    date_time=start_time,
                    temp=details[Detail.TEMPERATURE],
                    humidity=details[Detail.RELATIVE_HUMIDITY],
                    wind_speed=details[Detail.WIND_SPEED],
                    pollen=None,
                )
            )
        return result
