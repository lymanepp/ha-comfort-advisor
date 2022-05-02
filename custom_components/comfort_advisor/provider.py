"""Weather provider abstraction layer."""
from __future__ import annotations

from abc import ABCMeta, abstractmethod
from datetime import datetime
import logging
from typing import NamedTuple

from homeassistant.core import HomeAssistant
from homeassistant.util.decorator import Registry
import voluptuous as vol
from voluptuous.humanize import humanize_error

from .const import CONF_PROVIDER_TYPE, PROVIDER_TYPES
from .helpers import load_module
from .schemas import build_provider_schema

_LOGGER = logging.getLogger(__name__)

PROVIDERS: Registry[str, type[Provider]] = Registry()

PROVIDER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PROVIDER_TYPE): vol.In(PROVIDER_TYPES),
    },
    extra=vol.ALLOW_EXTRA,
)


class WeatherData(NamedTuple):
    """Data format returned by weather provider."""

    date_time: datetime
    temp: float
    humidity: float
    wind_speed: float
    pollen: int | None


class ProviderError(Exception):
    """Weather provider error."""

    def __init__(self, error_key: str, extra_info: str | None = None) -> None:
        """Initialize weather provider error."""
        super().__init__()
        self.error_key = error_key
        self.extra_info = extra_info


class Provider(metaclass=ABCMeta):
    """Abstract weather provider."""

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


async def provider_from_config(  # type: ignore
    hass: HomeAssistant, *, provider_type: str, **kwargs
) -> Provider | None:
    """Initialize a weather provider from a config."""

    config = {CONF_PROVIDER_TYPE: provider_type, **kwargs}

    try:
        schema = build_provider_schema()
        module = await load_module(hass, provider_type)
        provider_schema: vol.Schema = module.build_schema(hass, **kwargs)
        schema = schema.extend(provider_schema.schema, extra=vol.PREVENT_EXTRA)
        schema(config)
    except vol.Invalid as exc:
        _LOGGER.error(
            "Invalid configuration for weather provider: %s",
            humanize_error(config, exc),
        )
        return None
    except ImportError as exc:
        _LOGGER.error("Unable to load provider: %s, %s", provider_type, exc)
        return None

    provider_factory = PROVIDERS[provider_type]
    provider = provider_factory(hass, **config)
    assert isinstance(provider, Provider)
    return provider
