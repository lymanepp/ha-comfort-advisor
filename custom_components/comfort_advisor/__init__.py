"""Custom integration to integrate comfort_advisor with Home Assistant.

For more details about this integration, please refer to
https://github.com/lymanepp/ha-comfort-advisor
"""
from __future__ import annotations

import logging
from typing import Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
import voluptuous as vol

from .const import CONF_PROVIDER, DOMAIN, SCAN_INTERVAL_FORECAST, SCAN_INTERVAL_REALTIME
from .device import ComfortAdvisorDevice
from .provider import WeatherData, provider_from_config
from .schemas import build_schema

_LOGGER = logging.getLogger(__name__)

PLATFORMS: Final = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up entry configured from user interface."""
    hass.data.setdefault(DOMAIN, {})
    config = entry.data | entry.options or {}

    if entry.unique_id is None:
        # We have no unique_id yet, let's use backup.
        hass.config_entries.async_update_entry(entry, unique_id=entry.entry_id)

    try:
        build_schema(hass)(config)
    except vol.Invalid as exc:
        _LOGGER.error("Invalid configuration: %s", exc)
        return False

    if not (provider := await provider_from_config(hass, **config[CONF_PROVIDER])):
        return False

    realtime_service = DataUpdateCoordinator[WeatherData](
        hass,
        _LOGGER,
        name=f"{DOMAIN}_realtime_service",
        update_interval=SCAN_INTERVAL_REALTIME,
        update_method=provider.realtime,
    )

    forecast_service = DataUpdateCoordinator[list[WeatherData]](
        hass,
        _LOGGER,
        name=f"{DOMAIN}_forecast_service",
        update_interval=SCAN_INTERVAL_FORECAST,
        update_method=provider.forecast,
    )

    hass.data[DOMAIN][entry.entry_id] = ComfortAdvisorDevice(
        hass=hass,
        config_entry=entry,
        provider=provider,
        realtime_service=realtime_service,
        forecast_service=forecast_service,
    )

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
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)  # type: ignore
