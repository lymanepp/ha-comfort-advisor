"""This is a work in progress until HA bumps pynws to 1.4.1+."""
from __future__ import annotations

import logging
from typing import Final

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import selector
from homeassistant.util.dt import parse_datetime, utcnow
from pynws import SimpleNWS, version as PYNWS_VERSION
from pynws.const import Detail
import voluptuous as vol

from .weather import (
    WEATHER_PROVIDERS,
    WeatherData,
    WeatherProvider,
    WeatherProviderError,
)

_LOGGER = logging.getLogger(__name__)

REQUIREMENTS: Final = ["pynws>=1.4.1"]
DESCRIPTION: Final = (
    "For now, an API Key can be anything. It is recommended to use a valid email address."
)
SCHEMA: Final = vol.Schema(
    {
        vol.Required("api_key"): str,
        vol.Required("location"): selector({"location": {"radius": False}}),
    },
    extra=vol.PREVENT_EXTRA,
)


def exception_handler(func):
    """Decorate TomorrowioV4 calls to handle exceptions."""

    async def handler(self, *args, **kwargs):
        try:
            return await func(self, *args, **kwargs)
        except Exception as exc:
            _LOGGER.exception("Error from pynws: %s", exc_info=exc)
            raise WeatherProviderError("unknown") from exc

    return handler


@WEATHER_PROVIDERS.register("nws")
class NwsWeatherProvider(WeatherProvider):
    """TODO."""

    def __init__(
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

        session = async_get_clientsession(hass)

        self._api = SimpleNWS(latitude, longitude, api_key, session)

    @property
    def attribution(self) -> str:
        """Return attribution to use in UI."""
        return "Forecast provided by the National Weather Service/NOAA"

    @property
    def version(self) -> str:
        """Return attribution to use in UI."""
        return PYNWS_VERSION  # type: ignore

    @exception_handler
    async def realtime(self) -> WeatherData:
        """TODO."""
        if not self._api.station:
            await self._api.set_station()
        await self._api.update_observation(limit=1)
        # obs = self._api.observation
        # TODO: map to WeatherData
        # return self._to_weather_data(utcnow().replace(microsecond=0), realtime)
        raise WeatherProviderError("api_error")

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
