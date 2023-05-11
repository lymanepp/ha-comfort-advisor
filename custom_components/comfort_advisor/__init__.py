"""Custom integration to integrate Comfort Advisor with Home Assistant.

For more details about this integration, please refer to
https://github.com/lymanepp/ha-comfort-advisor
"""
from __future__ import annotations

from typing import Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
import voluptuous as vol

from .const import CONF_WEATHER, DOMAIN, LOGGER
from .device import ComfortAdvisorDevice
from .provider import async_create_weather_provider
from .schemas import DATA_SCHEMA

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
        LOGGER.error("Invalid configuration: %s", exc)
        return False

    # TODO: move into ComfortAdvisorDevice.__init__
    if not (provider := await async_create_weather_provider(hass, config[CONF_WEATHER])):
        return False

    device = ComfortAdvisorDevice(hass, config_entry, provider)
    if not await device.async_setup_entry(config_entry):
        return False
    hass.data[DOMAIN][config_entry.entry_id] = device

    hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

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
