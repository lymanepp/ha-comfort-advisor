"""Test setup process."""
from unittest.mock import AsyncMock, MagicMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.comfort_advisor import (
    PLATFORMS,
    async_setup_entry,
    async_unload_entry,
    async_update_options,
)
from custom_components.comfort_advisor.const import DOMAIN

from .const import ADVANCED_USER_INPUT


async def test_setup_update_unload_entry(hass):
    """Test entry setup and unload."""

    hass.config_entries.async_setup_platforms = MagicMock()
    with patch.object(hass.config_entries, "async_update_entry") as p:
        config_entry = MockConfigEntry(
            domain=DOMAIN, data=ADVANCED_USER_INPUT, entry_id="test", unique_id=None
        )
        await hass.config_entries.async_add(config_entry)
        assert p.called

    assert await async_setup_entry(hass, config_entry)
    assert DOMAIN in hass.data and config_entry.entry_id in hass.data[DOMAIN]

    # check user input is in config
    # TODO: this needs to be updated
    for key, value in ADVANCED_USER_INPUT.items():
        if key in hass.data[DOMAIN][config_entry.entry_id]:
            assert hass.data[DOMAIN][config_entry.entry_id][key] == value

    hass.config_entries.async_setup_platforms.assert_called_with(config_entry, PLATFORMS)

    # TODO: this needs to be updated
    # ToDo test hass.data[DOMAIN][config_entry.entry_id][UPDATE_LISTENER]

    hass.config_entries.async_reload = AsyncMock()
    assert await async_update_options(hass, config_entry) is None
    hass.config_entries.async_reload.assert_called_with(config_entry.entry_id)

    # Unload the entry and verify that the data has been removed
    assert await async_unload_entry(hass, config_entry)
    assert config_entry.entry_id not in hass.data[DOMAIN]
