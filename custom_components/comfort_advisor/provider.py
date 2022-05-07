"""Weather provider abstraction layer."""
from __future__ import annotations

from abc import ABCMeta, abstractmethod
from datetime import datetime
import json
import logging
from typing import Any, Mapping, NamedTuple, Sequence

from homeassistant.const import CONF_TYPE
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util.decorator import Registry

from .const import CONF_PROVIDER, DOMAIN, SCAN_INTERVAL_FORECAST, SCAN_INTERVAL_REALTIME
from .helpers import load_module

_LOGGER = logging.getLogger(__name__)

PROVIDERS: Registry[str, type[Provider]] = Registry()


class WeatherData(NamedTuple):
    """Data format returned by weather provider."""

    date_time: datetime
    temp: float
    humidity: float
    wind_speed: float
    pollen: int | None


class ProviderError(UpdateFailed):  # type:ignore
    """Weather provider error."""

    def __init__(self, error_key: str, extra_info: str | None = None) -> None:
        """Initialize weather provider error."""
        super().__init__()
        self.error_key = error_key
        self.extra_info = extra_info


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


async def async_get_provider(hass: HomeAssistant, config: Mapping[str, Any]) -> Provider:
    """Initialize a weather provider from a config."""

    providers: dict[str, Provider] = hass.data[DOMAIN].setdefault("providers", {})
    provider_config = config[CONF_PROVIDER]
    hashable_key = json.dumps(provider_config, sort_keys=True)

    if (provider := providers.get(hashable_key)) is not None:
        return provider

    type_ = provider_config[CONF_TYPE]

    try:
        await load_module(hass, type_)
    except ImportError as exc:
        _LOGGER.error("Unable to load provider: %s, %s", type_, exc)
        raise ProviderError("import_error") from exc

    # TODO: might need to move providers into their own folders with __init__.py only
    #       containing `REQUIREMENTS` and human-readble name. Could then auto-detect
    #       all supported providers.
    factory = PROVIDERS[type_]
    provider = factory(hass, provider_config)
    assert isinstance(provider, Provider)

    providers[hashable_key] = provider
    return provider
