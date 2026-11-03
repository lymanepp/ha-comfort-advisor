"""Tests for setting up the integration and its sensors."""

from datetime import datetime

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.comfort_advisor.formulas import calc_simmer_index

from .conftest import ENTRY_DATA, HOT, NICE, MockWeather, set_sensors

CAN_OPEN_WINDOWS = "sensor.comfort_advisor_can_open_windows"
CLOSE_WINDOWS_AT = "sensor.comfort_advisor_close_windows_at"
OPEN_WINDOWS_AT = "sensor.comfort_advisor_open_windows_at"
SIMMER_INDEX = "sensor.comfort_advisor_simmer_index"
HIGH_SIMMER_INDEX = "sensor.comfort_advisor_high_simmer_index"

pytestmark = pytest.mark.usefixtures("weather", "sensors")


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the config entry and wait for the first calculation."""
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_creates_sensors(hass: HomeAssistant, config_entry: MockConfigEntry):
    """All sensors are created and calculated from the inputs."""
    await setup_entry(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    entries = er.async_entries_for_config_entry(er.async_get(hass), config_entry.entry_id)
    assert len(entries) == 10

    assert hass.states.get(CAN_OPEN_WINDOWS).state == "on"
    assert hass.states.get(CAN_OPEN_WINDOWS).attributes["reason"] == "fresh_air"
    assert hass.states.get(CLOSE_WINDOWS_AT).state == STATE_UNKNOWN
    assert float(hass.states.get(SIMMER_INDEX).state) == pytest.approx(
        calc_simmer_index(*NICE, "°C")
    )
    assert hass.states.get(SIMMER_INDEX).attributes["unit_of_measurement"] == "°C"


async def test_device(hass: HomeAssistant, config_entry: MockConfigEntry):
    """A service device is registered for the entry."""
    await setup_entry(hass, config_entry)
    device = dr.async_get(hass).async_get_device_by_identifier(
        ("comfort_advisor", "test"), config_entry.entry_id
    )
    assert device
    assert device.name == "Comfort Advisor"
    assert device.entry_type is dr.DeviceEntryType.SERVICE
    assert device.sw_version == "0.0.1"  # from manifest.json


async def test_sensor_change_updates_state(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer
):
    """Changing an input sensor recalculates on the next update cycle."""
    await setup_entry(hass, config_entry)
    assert hass.states.get(CAN_OPEN_WINDOWS).state == "on"

    set_sensors(hass, outdoor=HOT)
    freezer.tick(60)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(CAN_OPEN_WINDOWS).state == "off"
    assert hass.states.get(CAN_OPEN_WINDOWS).attributes["reason"] == "uncomfortable"


async def test_forecast_drives_change_times(
    hass: HomeAssistant, config_entry: MockConfigEntry, weather: MockWeather
):
    """The close time comes from the first uncomfortable forecast hour."""
    weather.samples = [NICE, NICE, HOT, HOT]
    await setup_entry(hass, config_entry)

    close_at = datetime.fromisoformat(hass.states.get(CLOSE_WINDOWS_AT).state)
    forecast = await weather.async_forecast_hourly()
    assert close_at == datetime.fromisoformat(forecast[2]["datetime"])
    assert hass.states.get(OPEN_WINDOWS_AT).state == STATE_UNKNOWN
    assert float(hass.states.get(HIGH_SIMMER_INDEX).state) > 29.5


async def test_disabled_sensors(hass: HomeAssistant):
    """Sensors not chosen during setup are disabled by default."""
    entry = MockConfigEntry(
        domain="comfort_advisor",
        data=ENTRY_DATA | {"enabled_sensors": ["can_open_windows"]},
        unique_id="test2",
    )
    entry.add_to_hass(hass)
    await setup_entry(hass, entry)

    entries = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    enabled = [e.entity_id for e in entries if not e.disabled]
    assert enabled == [CAN_OPEN_WINDOWS]


async def test_unload(hass: HomeAssistant, config_entry: MockConfigEntry):
    """The entry unloads cleanly."""
    await setup_entry(hass, config_entry)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.NOT_LOADED
