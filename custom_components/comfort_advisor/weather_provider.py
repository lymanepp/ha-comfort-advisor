"""Weather provider abstraction layer."""
from __future__ import annotations

from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any
import logging

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
class WeatherData:
    """Data format returned by weather provider."""

    date_time: datetime
    temp: float
    humidity: float | None
    wind_speed: float | None
    pollen: float | None


class WeatherProviderError(Exception):
    """Weather provider error."""

    def __init__(self, error_key: str, extra_info: str | None = None) -> None:
        """Initialize weather provider error."""
        super().__init__()
        self.error_key = error_key
        self.extra_info = extra_info


class WeatherProvider(metaclass=ABCMeta):
    """Abstract weather provider."""

    @abstractmethod
    async def realtime(self) -> WeatherData:
        """Retrieve realtime weather from provider."""
        raise NotImplementedError

    @abstractmethod
    async def forecast(self) -> list[WeatherData]:
        """Retrieve weather forecast from provider."""
        raise NotImplementedError


async def weather_provider_from_config(
    hass: HomeAssistant, config: dict[str, Any]
) -> WeatherProvider:
    """Initialize a weather provider from a config."""
    provider_config: str = config.get(CONF_WEATHER_PROVIDER)
    if not provider_config:
        raise WeatherProviderError("missing_config")

    try:
        module_name: str = provider_config.pop(CONF_TYPE)
    except KeyError as exc:
        raise WeatherProviderError("invalid_config") from exc

    try:
        module = await load_module(hass, module_name)
    except ImportError as exc:
        raise WeatherProviderError("provider_not_found", module_name) from exc

    try:
        config = module.CONFIG_SCHEMA(provider_config)
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
