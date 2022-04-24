"""TODO."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from aiohttp import ClientSession
from pytomorrowio import TomorrowioV4

from homeassistant.util.dt import parse_datetime, utcnow

from .provider import ComfortData, Provider

TMRW_ATTR_TIMESTAMP = "startTime"
TMRW_ATTR_TEMPERATURE = "temperature"
TMRW_ATTR_HUMIDITY = "humidity"
TMRW_ATTR_WIND_SPEED = "windSpeed"
TMRW_ATTR_EPA_AQI = "epaIndex"
TMRW_ATTR_POLLEN_TREE = "treeIndex"
TMRW_ATTR_POLLEN_WEED = "weedIndex"
TMRW_ATTR_POLLEN_GRASS = "grassIndex"

FIELDS = [
    TMRW_ATTR_TEMPERATURE,
    TMRW_ATTR_HUMIDITY,
    TMRW_ATTR_WIND_SPEED,
    TMRW_ATTR_EPA_AQI,
    TMRW_ATTR_POLLEN_GRASS,
    TMRW_ATTR_POLLEN_TREE,
    TMRW_ATTR_POLLEN_WEED,
]


class TomorrowioProvider(Provider):
    """TODO."""

    def __init__(
        self,
        apikey: str,
        latitude: str | float | int,
        longitude: str | float | int,
        unit_system: str,
        session: ClientSession,
    ) -> None:
        """TODO."""
        self._api = TomorrowioV4(
            apikey=apikey,
            latitude=latitude,
            longitude=longitude,
            unit_system=unit_system,
            session=session,
        )

    @staticmethod
    def _map_to_comfort_data(
        date_time: datetime, values: dict[str, Any]
    ) -> ComfortData:
        return ComfortData(
            date_time=date_time,
            temp=values[TMRW_ATTR_TEMPERATURE],
            humidity=values.get(TMRW_ATTR_HUMIDITY),
            wind_speed=values.get(TMRW_ATTR_WIND_SPEED),
            aqi=values.get(TMRW_ATTR_EPA_AQI),
            pollen=max(
                values.get(TMRW_ATTR_POLLEN_TREE) or 0,
                values.get(TMRW_ATTR_POLLEN_WEED) or 0,
                values.get(TMRW_ATTR_POLLEN_GRASS) or 0,
            ),
        )

    async def realtime(self) -> ComfortData:
        """TODO."""
        realtime = await self._api.realtime(FIELDS)
        return self._map_to_comfort_data(utcnow(), realtime)

    async def forecast(self) -> list[ComfortData]:
        """TODO."""
        forecast = await self._api.forecast_hourly(FIELDS, start_time=utcnow())
        data: list[ComfortData] = []
        for entry in forecast:
            start_time = parse_datetime(entry.get(TMRW_ATTR_TIMESTAMP))
            values = entry.get("values")
            if not (start_time and values):
                break
            data.append(self._map_to_comfort_data(start_time, values))
        return data
