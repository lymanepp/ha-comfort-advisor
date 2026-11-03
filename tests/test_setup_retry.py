"""Tests for setup when the weather entity isn't available yet."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from .conftest import async_setup_weather

pytestmark = pytest.mark.usefixtures("sensors")


async def test_retries_until_weather_entity_exists(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
):
    """Setup is retried while the weather entity doesn't exist, then succeeds."""
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    assert "weather.test_weather" in config_entry.reason
    assert hass.states.get("sensor.comfort_advisor_can_open_windows") is None

    await async_setup_weather(hass)
    freezer.tick(timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.comfort_advisor_can_open_windows").state == "on"
