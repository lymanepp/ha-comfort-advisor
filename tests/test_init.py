"""Tests for setting up the integration and its sensors."""

from datetime import datetime, timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
    EVENT_STATE_CHANGED,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    EntityCategory,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
)

from custom_components.comfort_advisor.formulas import calc_simmer_index

from .conftest import (
    ENTRY_DATA,
    HOT,
    INDOOR_HUMIDITY,
    NICE,
    OUTDOOR_HUMIDITY,
    OUTDOOR_TEMPERATURE,
    MockWeather,
    set_sensors,
)

CAN_OPEN_WINDOWS = "binary_sensor.comfort_advisor_can_open_windows"
CLOSE_WINDOWS_AT = "sensor.comfort_advisor_close_windows_at"
OPEN_WINDOWS_AT = "sensor.comfort_advisor_open_windows_at"
SIMMER_INDEX = "sensor.comfort_advisor_simmer_index"
HIGH_SIMMER_INDEX = "sensor.comfort_advisor_high_simmer_index"

pytestmark = pytest.mark.usefixtures("weather", "sensors")

TEMPERATURE_ATTRS = {ATTR_DEVICE_CLASS: "temperature", ATTR_UNIT_OF_MEASUREMENT: "°C"}
HUMIDITY_ATTRS = {ATTR_DEVICE_CLASS: "humidity", ATTR_UNIT_OF_MEASUREMENT: "%"}


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the config entry and wait for the first calculation."""
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_creates_sensors(hass: HomeAssistant, config_entry: MockConfigEntry):
    """All sensors are created and calculated from the inputs."""
    await setup_entry(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    entries = er.async_entries_for_config_entry(er.async_get(hass), config_entry.entry_id)
    assert len(entries) == 13

    assert hass.states.get(CAN_OPEN_WINDOWS).state == "on"
    assert hass.states.get(CAN_OPEN_WINDOWS).attributes["reason"] == "fresh_air"
    assert hass.states.get(CLOSE_WINDOWS_AT).state == STATE_UNKNOWN
    assert float(hass.states.get(SIMMER_INDEX).state) == round(calc_simmer_index(*NICE, "°C"), 1)
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


async def poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory, delta=timedelta(seconds=60)):
    """Advance time past the next update cycle."""
    freezer.tick(delta)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_unavailable_sensor_makes_outputs_unavailable(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
):
    """Outputs follow an input sensor into and out of unavailability."""
    await setup_entry(hass, config_entry)

    hass.states.async_set(OUTDOOR_TEMPERATURE, STATE_UNAVAILABLE)
    await poll(hass, freezer)
    assert hass.states.get(CAN_OPEN_WINDOWS).state == STATE_UNAVAILABLE
    assert hass.states.get(SIMMER_INDEX).state == STATE_UNAVAILABLE

    set_sensors(hass)
    await poll(hass, freezer)
    assert hass.states.get(CAN_OPEN_WINDOWS).state == "on"


async def test_removed_sensor_makes_outputs_unavailable(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
):
    """A removed input sensor doesn't crash the update and clears the outputs."""
    await setup_entry(hass, config_entry)

    hass.states.async_remove(INDOOR_HUMIDITY)
    await poll(hass, freezer)
    assert hass.states.get(CAN_OPEN_WINDOWS).state == STATE_UNAVAILABLE


async def test_empty_forecast_makes_outputs_unavailable(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    weather: MockWeather,
    freezer: FrozenDateTimeFactory,
):
    """A weather provider returning no forecast clears the outputs."""
    await setup_entry(hass, config_entry)

    weather.samples = []
    await weather.async_update_listeners(["hourly"])
    await poll(hass, freezer)
    assert hass.states.get(CAN_OPEN_WINDOWS).state == STATE_UNAVAILABLE


async def test_close_time_moves_forward_when_it_passes(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    weather: MockWeather,
    freezer: FrozenDateTimeFactory,
):
    """Without any input change, a passed close time is replaced by the next one."""
    weather.samples = [NICE, NICE, HOT, NICE, HOT]
    await setup_entry(hass, config_entry)
    forecast = await weather.async_forecast_hourly()
    close_at = datetime.fromisoformat(hass.states.get(CLOSE_WINDOWS_AT).state)
    assert close_at == datetime.fromisoformat(forecast[2]["datetime"])

    # The outdoor sensor still reads NICE after the forecast said HOT.
    freezer.move_to(close_at + timedelta(minutes=1))
    await poll(hass, freezer)
    new_close_at = datetime.fromisoformat(hass.states.get(CLOSE_WINDOWS_AT).state)
    assert new_close_at == datetime.fromisoformat(forecast[4]["datetime"])
    assert new_close_at > dt_util.utcnow()


async def test_temperature_and_humidity_are_combined(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
):
    """Temperature and humidity arriving together cause one recalculation."""
    await setup_entry(hass, config_entry)
    events = async_capture_events(hass, EVENT_STATE_CHANGED)

    hass.states.async_set(OUTDOOR_TEMPERATURE, "26.0", TEMPERATURE_ATTRS)
    freezer.tick(timedelta(milliseconds=500))
    hass.states.async_set(OUTDOOR_HUMIDITY, "60.0", HUMIDITY_ATTRS)
    await hass.async_block_till_done()

    # Nothing is published until the inputs have settled.
    assert not [e for e in events if e.data["entity_id"] == SIMMER_INDEX]

    await poll(hass, freezer, timedelta(seconds=1))
    changes = [e for e in events if e.data["entity_id"] == SIMMER_INDEX]
    assert len(changes) == 1
    assert float(changes[0].data["new_state"].state) == round(
        calc_simmer_index(26.0, 60.0, "°C"), 1
    )


async def test_tiny_change_records_no_new_state(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
):
    """A change too small to affect the rounded outputs records nothing."""
    await setup_entry(hass, config_entry)
    events = async_capture_events(hass, EVENT_STATE_CHANGED)

    hass.states.async_set(OUTDOOR_TEMPERATURE, str(NICE[0] + 0.001), TEMPERATURE_ATTRS)
    await poll(hass, freezer, timedelta(seconds=1))

    assert [e.data["entity_id"] for e in events] == [OUTDOOR_TEMPERATURE]


async def test_recalculates_when_forecast_hour_arrives(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    weather: MockWeather,
    freezer: FrozenDateTimeFactory,
):
    """Without any input change, a forecast hour that arrives leaves the forecast."""
    weather.samples = [HOT] + [NICE] * 23
    await setup_entry(hass, config_entry)
    forecast = await weather.async_forecast_hourly()
    high_with_hot_hour = float(hass.states.get(HIGH_SIMMER_INDEX).state)

    freezer.move_to(datetime.fromisoformat(forecast[0]["datetime"]))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert float(hass.states.get(HIGH_SIMMER_INDEX).state) < high_with_hot_hour


async def test_unload_cancels_timers(hass: HomeAssistant, config_entry: MockConfigEntry):
    """Unloading cancels the pending recalculation and the forecast-hour timer."""
    await setup_entry(hass, config_entry)
    device = config_entry.runtime_data
    assert device._expiry_timer is not None  # pylint: disable=protected-access

    set_sensors(hass, outdoor=HOT)  # leaves a recalculation pending
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    assert device._expiry_timer is None  # pylint: disable=protected-access
    assert device._debouncer._timer_task is None  # pylint: disable=protected-access


async def test_can_open_windows_is_a_binary_sensor(
    hass: HomeAssistant, config_entry: MockConfigEntry
):
    """The can-open-windows entity is a binary sensor with translated name and states."""
    await setup_entry(hass, config_entry)
    entry = er.async_get(hass).async_get(CAN_OPEN_WINDOWS)
    assert entry
    assert entry.unique_id == "test_can_open_windows"
    assert entry.translation_key == "can_open_windows"
    assert entry.original_device_class is None  # "window" would show Open/Closed
    assert hass.states.get(CAN_OPEN_WINDOWS).name == "Comfort Advisor Can open windows"
    assert hass.states.get("sensor.comfort_advisor_can_open_windows") is None


async def test_old_can_open_windows_sensor_is_removed(
    hass: HomeAssistant, config_entry: MockConfigEntry
):
    """The registry entry of the former "can open windows" sensor is removed."""
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "sensor",
        "comfort_advisor",
        "test_can_open_windows",
        config_entry=config_entry,
        suggested_object_id="comfort_advisor_can_open_windows",
    )
    assert old.entity_id == "sensor.comfort_advisor_can_open_windows"

    await setup_entry(hass, config_entry)

    assert registry.async_get(old.entity_id) is None
    assert registry.async_get(CAN_OPEN_WINDOWS)
    assert hass.states.get(CAN_OPEN_WINDOWS).state == "on"


async def test_forecast_offset_sensors(hass: HomeAssistant, config_entry: MockConfigEntry):
    """The forecast offsets are diagnostic temperature-difference sensors."""
    await setup_entry(hass, config_entry)
    registry = er.async_get(hass)
    for entity_id in (
        "sensor.comfort_advisor_forecast_temperature_offset",
        "sensor.comfort_advisor_forecast_dew_point_offset",
    ):
        entry = registry.async_get(entity_id)
        assert entry
        assert entry.entity_category is EntityCategory.DIAGNOSTIC
        assert entry.original_device_class == "temperature_delta"
        state = hass.states.get(entity_id)
        assert state.attributes["unit_of_measurement"] == "°C"
        # The outdoor sensors read exactly the forecast's first hour.
        assert float(state.state) == 0.0


async def test_open_time_remaining_sensor(
    hass: HomeAssistant, config_entry: MockConfigEntry, weather: MockWeather
):
    """The open time remaining is a duration sensor in hours."""
    weather.samples = [NICE, NICE, HOT]
    await setup_entry(hass, config_entry)
    state = hass.states.get("sensor.comfort_advisor_open_time_remaining")
    assert state.attributes["device_class"] == "duration"
    assert state.attributes["unit_of_measurement"] == "h"
    close_at = datetime.fromisoformat(hass.states.get(CLOSE_WINDOWS_AT).state)
    hours = (close_at - dt_util.utcnow()).total_seconds() / 3600
    assert abs(float(state.state) - hours) <= 0.25


async def test_pollen_sensors(hass: HomeAssistant, freezer: FrozenDateTimeFactory):
    """The highest pollen level counts; unavailable pollen sensors are ignored."""
    hass.states.async_set("sensor.grass_pollen", "1")
    hass.states.async_set("sensor.tree_pollen", "Very High")
    entry = MockConfigEntry(
        domain="comfort_advisor",
        data=ENTRY_DATA | {"pollen": ["sensor.grass_pollen", "sensor.tree_pollen"]},
        unique_id="test",
    )
    entry.add_to_hass(hass)
    await setup_entry(hass, entry)
    assert hass.states.get(CAN_OPEN_WINDOWS).state == "off"
    assert hass.states.get(CAN_OPEN_WINDOWS).attributes["reason"] == "high_pollen"

    hass.states.async_set("sensor.tree_pollen", STATE_UNAVAILABLE)
    await poll(hass, freezer, timedelta(seconds=1))
    assert hass.states.get(CAN_OPEN_WINDOWS).state == "on"  # grass "1" is within "low"

    hass.states.async_set("sensor.grass_pollen", "3")
    await poll(hass, freezer, timedelta(seconds=1))
    assert hass.states.get(CAN_OPEN_WINDOWS).state == "off"


async def test_iqvia_allergy_index(hass: HomeAssistant, freezer: FrozenDateTimeFactory):
    """An IQVIA allergy index (0-12) is recognized and converted."""
    iqvia = er.async_get(hass).async_get_or_create(
        "sensor", "iqvia", "10001_allergy_index_today", suggested_object_id="allergy_index_today"
    )
    hass.states.async_set(iqvia.entity_id, "7.5")  # Medium-High: level 4
    entry = MockConfigEntry(
        domain="comfort_advisor",
        data=ENTRY_DATA | {"pollen": [iqvia.entity_id]},
        unique_id="test",
    )
    entry.add_to_hass(hass)
    await setup_entry(hass, entry)
    assert hass.states.get(CAN_OPEN_WINDOWS).attributes["reason"] == "high_pollen"

    hass.states.async_set(iqvia.entity_id, "4.0")  # Low-Medium: level 2, the maximum
    await poll(hass, freezer, timedelta(seconds=1))
    assert hass.states.get(CAN_OPEN_WINDOWS).state == "on"
