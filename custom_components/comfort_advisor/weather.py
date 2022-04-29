"""Weather provider abstraction layer."""
from __future__ import annotations

from abc import ABCMeta, abstractmethod
from datetime import datetime
import logging
from typing import Any, NamedTuple

from homeassistant.core import HomeAssistant
from homeassistant.util.decorator import Registry
import voluptuous as vol
from voluptuous.humanize import humanize_error

from .const import WEATHER_PROVIDER_TYPES, ConfigValue
from .helpers import load_module

_LOGGER = logging.getLogger(__name__)

WEATHER_PROVIDERS: Registry[str, type[WeatherProvider]] = Registry()

WEATHER_PROVIDER_SCHEMA = vol.Schema(
    {
        vol.Required(str(ConfigValue.PROVIDER_TYPE)): vol.In(WEATHER_PROVIDER_TYPES),
    },
    extra=vol.ALLOW_EXTRA,
)


class WeatherData(NamedTuple):
    """Data format returned by weather provider."""

    date_time: datetime
    temp: float
    humidity: float
    wind_speed: float
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

    def __init__(self, *, provider_type: str):
        """Eat the `provider_type` kwarg."""

    @property
    @abstractmethod
    def attribution(self) -> str:
        """Return attribution."""
        raise NotImplementedError

    @property
    @abstractmethod
    def version(self) -> str:
        """Return dependency version."""
        raise NotImplementedError

    @abstractmethod
    async def realtime(self) -> WeatherData:
        """Retrieve realtime weather from provider."""
        raise NotImplementedError

    @abstractmethod
    async def forecast(self) -> list[WeatherData]:
        """Retrieve weather forecast from provider."""
        raise NotImplementedError


async def weather_provider_from_config(
    hass: HomeAssistant, provider_config: dict[str, Any]
) -> WeatherProvider:
    """Initialize a weather provider from a config."""

    try:
        WEATHER_PROVIDER_SCHEMA(provider_config)
        provider_type: str = provider_config[ConfigValue.PROVIDER_TYPE]
        module = await load_module(hass, provider_type)
        schema = WEATHER_PROVIDER_SCHEMA.extend(module.SCHEMA.schema, extra=vol.PREVENT_EXTRA)
        schema(provider_config)
    except vol.Invalid as exc:
        _LOGGER.error(
            "Invalid configuration for weather provider: %s",
            humanize_error(provider_config, exc),
        )
        raise WeatherProviderError("invalid_config") from exc
    except ImportError as exc:
        raise WeatherProviderError("import_error") from exc

    provider_factory = WEATHER_PROVIDERS[provider_type]
    provider = provider_factory(hass, **provider_config)
    assert isinstance(provider, WeatherProvider)
    return provider
