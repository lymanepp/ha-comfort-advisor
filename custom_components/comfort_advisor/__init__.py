"""Custom integration to integrate Comfort Advisor with Home Assistant.

For more details about this integration, please refer to
https://github.com/lymanepp/ha-comfort-advisor
"""
from __future__ import annotations

from typing import Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.start import async_at_start

from .const import DOMAIN
from .device import ComfortAdvisorDevice

PLATFORMS: Final = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up entry configured from user interface."""
    hass.data.setdefault(DOMAIN, {})

    if config_entry.unique_id is None:
        # We have no unique_id yet, let's use backup.
        hass.config_entries.async_update_entry(config_entry, unique_id=config_entry.entry_id)

    device = ComfortAdvisorDevice(hass, config_entry)
    hass.data[DOMAIN][config_entry.entry_id] = device

    async def on_started(hass: HomeAssistant):
        await device.async_setup_entry(config_entry)

    config_entry.async_on_unload(async_at_start(hass, on_started))

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    config_entry.async_on_unload(config_entry.add_update_listener(async_update_options))
    return True


async def async_update_options(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Update options from user interface."""
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Remove entry via user interface."""
    hass.data[DOMAIN].pop(config_entry.entry_id)
    return await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)  # type: ignore
