"""TODO."""
from __future__ import annotations

from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from datetime import datetime
import importlib
import logging
from types import ModuleType
from typing import Any, TypedDict

from homeassistant import requirements
from homeassistant.const import CONF_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.util.decorator import Registry
import voluptuous as vol
from voluptuous.humanize import humanize_error

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DATA_REQS = "reqs_processed"

WEATHER_PROVIDERS: Registry[str, type[WeatherProvider]] = Registry()

WEATHER_PROVIDER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TYPE): str,
    },
    extra=vol.ALLOW_EXTRA,
)

WEATHER_PROVIDER_NAMES = ["tomorrowio", "fake"]


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
    provider_name: str = config[CONF_TYPE]
    module = await load_weather_provider_module(hass, provider_name)

    try:
        config = module.CONFIG_SCHEMA(config)
    except vol.Invalid as err:
        _LOGGER.error(
            "Invalid configuration for weather provider %s: %s",
            provider_name,
            humanize_error(config, err),
        )
        raise

    # TODO: use factory method instead of Registry?
    if (create_provider := WEATHER_PROVIDERS.get(provider_name)) is None:
        raise WeatherProviderError(f"Weather provider '{provider_name}' was not found")

    return create_provider(hass, **config)


async def load_weather_provider_module(
    hass: HomeAssistant, provider: str
) -> ModuleType:
    """Load a weather provider."""
    try:
        module = importlib.import_module(
            f"custom_components.comfort_advisor.weather_providers.{provider}"
        )
    except ImportError as err:
        _LOGGER.error("Unable to load weather provider %s: %s", provider, err)
        raise WeatherProviderError(
            f"Unable to load weather provider {provider}: {err}"
        ) from err

    if hass.config.skip_pip or not hasattr(module, "REQUIREMENTS"):
        return module

    processed = hass.data[DOMAIN].setdefault(DATA_REQS, set())
    if provider in processed:
        return module

    reqs = module.REQUIREMENTS
    await requirements.async_process_requirements(
        hass, f"weather provider {provider}", reqs
    )

    processed.add(provider)
    return module
