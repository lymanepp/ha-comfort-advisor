"""TODO."""
from __future__ import annotations

from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any, TypedDict

from homeassistant.const import CONF_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.util.decorator import Registry
import voluptuous as vol
from voluptuous.humanize import humanize_error

from .const import CONF_WEATHER_PROVIDER
from .helpers import load_module

_LOGGER = logging.getLogger(__name__)

WEATHER_PROVIDERS: Registry[str, type[WeatherProvider]] = Registry()

WEATHER_PROVIDER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TYPE): str,
    },
    extra=vol.ALLOW_EXTRA,
)


@dataclass
class WeatherData(TypedDict, total=False):
    """TODO."""

    date_time: datetime
    temp: float
    humidity: float | None
    wind_speed: float | None
    pollen: float | None


class WeatherProviderError(Exception):
    """TODO."""

    def __init__(self, error_key: str, extra_info: str | None = None) -> None:
        """TODO."""
        super().__init__()
        self.error_key = error_key
        self.extra_info = extra_info


class WeatherProvider(metaclass=ABCMeta):
    """TODO."""

    @abstractmethod
    async def realtime(self) -> WeatherData:
        """TODO."""
        raise NotImplementedError

    @abstractmethod
    async def forecast(self) -> list[WeatherData]:
        """TODO."""
        raise NotImplementedError


async def weather_provider_from_config(
    hass: HomeAssistant, config: dict[str, Any]
) -> WeatherProvider:
    """Initialize a weather provider from a config."""
    weather_provider: str = config.get(CONF_WEATHER_PROVIDER)
    if not weather_provider:
        raise WeatherProviderError("missing_config")

    try:
        module_name: str = weather_provider.pop(CONF_TYPE)
    except KeyError as exc:
        raise WeatherProviderError("invalid_config") from exc

    try:
        module = await load_module(hass, module_name)
    except ImportError as exc:
        raise WeatherProviderError("provider_not_found", module_name) from exc

    try:
        config = module.CONFIG_SCHEMA(weather_provider)
    except vol.Invalid as exc:
        _LOGGER.error(
            "Invalid configuration for weather provider %s: %s",
            module_name,
            humanize_error(config, exc),
        )
        raise WeatherProviderError("invalid_config", module_name) from exc

    if (provider_factory := WEATHER_PROVIDERS.get(module_name)) is None:
        raise WeatherProviderError("provider_not_found", module_name)

    return provider_factory(hass, **config)
