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

from .const import CONF_PROVIDER, DOMAIN
from .device import ComfortAdvisorDevice
from .provider import provider_from_config
from .schemas import build_schema

_LOGGER = logging.getLogger(__name__)

PLATFORMS: Final = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up entry configured from user interface."""
    hass.data.setdefault(DOMAIN, {})
    config = config_entry.data | config_entry.options or {}

    if config_entry.unique_id is None:
        # We have no unique_id yet, let's use backup.
        hass.config_entries.async_update_entry(config_entry, unique_id=config_entry.entry_id)

    try:
        schema = build_schema(hass)
        schema(config)
    except vol.Invalid as exc:
        _LOGGER.error("Invalid configuration: %s", exc)
        return False

    if not (provider := await provider_from_config(hass, **config[CONF_PROVIDER])):
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
    return await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)  # type: ignore
