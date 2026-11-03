"""Custom integration to integrate Comfort Advisor with Home Assistant.

For more details about this integration, please refer to
https://github.com/lymanepp/ha-comfort-advisor
"""

from typing import Final

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN
from .device import ComfortAdvisorConfigEntry, ComfortAdvisorDevice

PLATFORMS: Final = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ComfortAdvisorConfigEntry) -> bool:
    """Set up entry configured from user interface."""
    if entry.unique_id is None:
        # We have no unique_id yet, let's use backup.
        hass.config_entries.async_update_entry(entry, unique_id=entry.entry_id)

    integration = await async_get_integration(hass, DOMAIN)
    device = ComfortAdvisorDevice(hass, entry, sw_version=str(integration.version))
    entry.runtime_data = device
    await device.async_setup_entry(entry)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True


async def async_update_options(hass: HomeAssistant, entry: ComfortAdvisorConfigEntry) -> None:
    """Update options from user interface."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ComfortAdvisorConfigEntry) -> bool:
    """Remove entry via user interface."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
