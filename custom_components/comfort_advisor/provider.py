"""Weather provider abstraction layer."""
from __future__ import annotations

from abc import ABCMeta, abstractmethod
import asyncio
from dataclasses import dataclass
from datetime import datetime
from functools import wraps
import importlib
import json
import logging
import sys
from typing import Any, Callable, Coroutine, Mapping, Sequence, TypeVar

from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.requirements import RequirementsNotFound, async_process_requirements
from homeassistant.util.decorator import Registry

from .const import CONF_PROVIDER, DOMAIN, SCAN_INTERVAL_FORECAST, SCAN_INTERVAL_REALTIME

if sys.version_info >= (3, 10):
    from typing import ParamSpec
else:
    from typing_extensions import ParamSpec

_P = ParamSpec("_P")
_T = TypeVar("_T")

_LOGGER = logging.getLogger(__name__)

PROVIDERS: Registry[str, type[Provider]] = Registry()

PROVIDER_META = {
    "nws": {
        "NAME": "National Weather Service/NOAA",
        "REQUIREMENTS": ["pynws>=1.4.1"],
        "DESCRIPTION": "For now, an API Key can be anything. It is recommended to use a valid email address.\n\nThe National Weather Service does not provide pollen data.",
    },
    "tomorrowio": {
        "NAME": "Tomorrow.io",
        "REQUIREMENTS": ["pytomorrowio>=0.3.1"],
        "DESCRIPTION": "To get an API key, sign up at [Tomorrow.io](https://app.tomorrow.io/signup).",
    },
}


@dataclass
class WeatherData:
    """Data format returned by weather provider."""

    date_time: datetime
    temp: float
    humidity: float
    wind_speed: float
    pollen: int | None


class ProviderException(UpdateFailed):  # type:ignore
    """Weather provider error."""

    def __init__(self, error_key: str, can_retry: bool = False) -> None:
        """Initialize weather provider error."""
        super().__init__()
        self.error_key = error_key
        self.can_retry = can_retry


def async_retry(
    wrapped: Callable[_P, Coroutine[Any, Any, _T]]
) -> Callable[_P, Coroutine[Any, Any, _T]]:
    """`ProviderError` retry handler."""

    @wraps(wrapped)
    async def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        retries = 5
        while True:
            try:
                return await wrapped(*args, **kwargs)
            except ProviderException as exc:
                if not exc.can_retry or retries == 0:
                    _LOGGER.exception("%r from weather provider", exc, exc_info=exc)
                    raise
                _LOGGER.debug("%r from weather provider: %d retries remaining", exc, retries)
                retries -= 1
            await asyncio.sleep(1)

    return wrapper


class Provider(metaclass=ABCMeta):
    """Abstract weather provider."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize."""
        self.hass = hass

        self.realtime_service = DataUpdateCoordinator[WeatherData](
            hass,
            _LOGGER,
            name=f"{DOMAIN}_realtime",
            update_interval=SCAN_INTERVAL_REALTIME,
            update_method=self.fetch_realtime,
        )
        self.forecast_service = DataUpdateCoordinator[list[WeatherData]](
            hass,
            _LOGGER,
            name=f"{DOMAIN}_forecast",
            update_interval=SCAN_INTERVAL_FORECAST,
            update_method=self.fetch_forecast,
        )

    def async_add_realtime_listener(self, update_callback: CALLBACK_TYPE) -> CALLBACK_TYPE:
        """Listen for data updates."""
        remover: CALLBACK_TYPE = self.realtime_service.async_add_listener(update_callback)
        if self.realtime_service.data is None:
            self.hass.async_create_task(self.realtime_service.async_config_entry_first_refresh())
        else:
            update_callback()
        return remover

    def async_add_forecast_listener(self, update_callback: CALLBACK_TYPE) -> CALLBACK_TYPE:
        """Listen for data updates."""
        remover: CALLBACK_TYPE = self.forecast_service.async_add_listener(update_callback)
        if self.forecast_service.data is None:
            self.hass.async_create_task(self.forecast_service.async_config_entry_first_refresh())
        else:
            update_callback()
        return remover

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
    async def fetch_realtime(self) -> WeatherData | None:
        """Retrieve realtime weather from provider."""
        raise NotImplementedError

    @abstractmethod
    async def fetch_forecast(self) -> Sequence[WeatherData] | None:
        """Retrieve weather forecast from provider."""
        raise NotImplementedError


async def async_create_weather_provider(
    hass: HomeAssistant, provider_config: Mapping[str, Any]
) -> Provider:
    """Initialize a weather provider from a config."""

    providers: dict[str, Provider] = hass.data.setdefault(DOMAIN, {}).setdefault("providers", {})
    hashable_key = json.dumps(provider_config, sort_keys=True)

    if (provider := providers.get(hashable_key)) is not None:
        return provider

    provider_type = provider_config[CONF_PROVIDER]

    if not (provider_meta := PROVIDER_META.get(provider_type)):
        raise ValueError("Invalid provider type")

    requirements = provider_meta["REQUIREMENTS"]

    try:
        await async_process_requirements(hass, f"module {provider_type}", requirements)
    except RequirementsNotFound as exc:
        _LOGGER.exception("Unable to satisfy requirements for %s", provider_type, exc_info=exc)
        raise

    try:
        # importing the provider will register type factory in `PROVIDERS`
        importlib.import_module(f"{__package__}.{provider_type}")
    except ImportError as exc:
        _LOGGER.exception("Unable to load module %s", provider_type, exc_info=exc)
        raise

    factory = PROVIDERS.get(provider_type)
    provider = factory(hass, provider_config)
    assert isinstance(provider, Provider)

    providers[hashable_key] = provider
    return provider
