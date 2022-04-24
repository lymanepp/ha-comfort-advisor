"""TODO."""
from __future__ import annotations

import abc
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ComfortData:
    """Data type returned by weather provider."""

    date_time: datetime
    temp: float
    humidity: float | None
    wind_speed: float | None
    aqi: float | None
    pollen: float | None


class ProviderError(Exception):  # TODO: need better base class
    """TODO."""


# Entities level
class Provider(metaclass=abc.ABCMeta):
    """TODO."""

    @abc.abstractmethod
    async def realtime(self) -> ComfortData:
        """TODO."""
        raise NotImplementedError

    @abc.abstractmethod
    async def forecast(self) -> list[ComfortData]:
        """TODO."""
        raise NotImplementedError
