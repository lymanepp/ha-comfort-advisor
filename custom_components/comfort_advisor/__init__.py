"""Custom integration to integrate Comfort Advisor with Home Assistant.

For more details about this integration, please refer to
https://github.com/lymanepp/ha-comfort-advisor
"""
from __future__ import annotations

import logging
from typing import Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
import voluptuous as vol

from .const import DOMAIN
from .device import ComfortAdvisorDevice
from .provider import async_get_provider
from .schemas import DATA_SCHEMA

_LOGGER = logging.getLogger(__name__)

PLATFORMS: Final = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up entry configured from user interface."""
    hass.data.setdefault(DOMAIN, {})
    config = config_entry.data | config_entry.options or {}

    if config_entry.unique_id is None:
        # We have no unique_id yet, let's use backup.
        hass.config_entries.async_update_entry(config_entry, unique_id=config_entry.entry_id)

    try:
        config = DATA_SCHEMA(config)
    except vol.Invalid as exc:
        _LOGGER.error("Invalid configuration: %s", exc)
        return False

    if not (provider := await async_get_provider(hass, config)):
        return False

    device = ComfortAdvisorDevice(hass, config_entry, provider)
    if not await device.async_setup_entry(config_entry):
        return False
    hass.data[DOMAIN][config_entry.entry_id] = device

    hass.config_entries.async_setup_platforms(config_entry, PLATFORMS)

    config_entry.async_on_unload(config_entry.add_update_listener(async_update_options))
    return True


async def async_update_options(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Update options from user interface."""
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Remove entry via user interface."""
    hass.data[DOMAIN].pop(config_entry.entry_id)
    # TODO: cleanup provider if last subscriber
    return await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)  # type: ignore
