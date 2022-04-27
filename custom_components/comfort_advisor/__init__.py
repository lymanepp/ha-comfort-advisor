"""Custom integration to integrate comfort_advisor with Home Assistant.

For more details about this integration, please refer to
https://github.com/lymanepp/ha-comfort-advisor
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS, SCAN_INTERVAL_FORECAST, SCAN_INTERVAL_REALTIME
from .device import (
    ComfortAdvisorDevice,
    ForecastDataUpdateCoordinator,
    RealtimeDataUpdateCoordinator,
)
from .weather_provider import weather_provider_from_config

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up entry configured from user interface."""
    hass.data[DOMAIN] = {}
    config = entry.data | entry.options or {}

    if entry.unique_id is None:
        # We have no unique_id yet, let's use backup.
        hass.config_entries.async_update_entry(entry, unique_id=entry.entry_id)

    weather_provider = await weather_provider_from_config(hass, config)

    realtime_service = RealtimeDataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_realtime_service",
        update_interval=SCAN_INTERVAL_REALTIME,
        update_method=weather_provider.realtime,
    )

    forecast_service = ForecastDataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_forecast_service",
        update_interval=SCAN_INTERVAL_FORECAST,
        update_method=weather_provider.forecast,
    )

    device = ComfortAdvisorDevice(
        hass=hass,
        config_entry=entry,
        realtime_service=realtime_service,
        forecast_service=forecast_service,
    )

    hass.data[DOMAIN][entry.entry_id] = device

    await realtime_service.async_config_entry_first_refresh()
    await forecast_service.async_config_entry_first_refresh()

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options from user interface."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove entry via user interface."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
