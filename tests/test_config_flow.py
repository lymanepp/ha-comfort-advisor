"""Test integration_blueprint config flow."""

import json
import pathlib
from unittest.mock import MagicMock, patch

from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_NAME
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import voluptuous as vol

from custom_components.comfort_advisor.const import (
    CONF_INDOOR_HUMIDITY,
    CONF_INDOOR_TEMPERATURE,
    CONF_OUTDOOR_HUMIDITY,
    CONF_OUTDOOR_TEMPERATURE,
    DOMAIN,
)

from .const import ADVANCED_USER_INPUT, USER_INPUT
from .test_sensor import DEFAULT_TEST_SENSORS


@pytest.fixture(autouse=True)
def bypass_setup_fixture():
    """Prevent setup."""
    with patch(
        "custom_components.comfort_advisor.async_setup_entry",
        return_value=True,
    ):
        yield


async def _flow_init(hass, advanced_options=True):
    return await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_USER,
            "show_advanced_options": advanced_options,
        },
    )


async def _flow_configure(hass, r, _input=ADVANCED_USER_INPUT):
    with patch(
        "homeassistant.helpers.entity_registry.EntityRegistry.async_get",
        return_value=MagicMock(unique_id="foo"),
    ):
        return await hass.config_entries.flow.async_configure(r["flow_id"], user_input=_input)


@pytest.mark.parametrize(*DEFAULT_TEST_SENSORS)
async def test_successful_config_flow(hass, start_ha):
    """Test a successful config flow."""
    # Initialize a config flow
    result = await _flow_init(hass)

    # Check that the config flow shows the user form as the first step
    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == "user"

    result = await _flow_configure(hass, result)

    assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY

    assert result["title"] == ADVANCED_USER_INPUT[CONF_NAME]
    assert result["data"] == ADVANCED_USER_INPUT
    assert result["result"]


@pytest.mark.parametrize(*DEFAULT_TEST_SENSORS)
async def test_failed_config_flow(hass, start_ha):
    """Config flow should fail if ..."""

    # We try to set up second instance for same temperature and humidity sensors
    for _ in [0, 1]:
        result = await _flow_init(hass)
        result = await _flow_configure(hass, result)

    assert result["type"] == data_entry_flow.RESULT_TYPE_ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize(*DEFAULT_TEST_SENSORS)
async def test_options_flow(hass, start_ha):
    """Test flow for options changes."""
    # setup entry
    entry = MockConfigEntry(domain=DOMAIN, data=ADVANCED_USER_INPUT, entry_id="test")
    entry.add_to_hass(hass)

    # Initialize an options flow for entry
    result = await hass.config_entries.options.async_init(
        entry.entry_id, context={"show_advanced_options": True}
    )

    # Verify that the first options step is a user form
    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == "init"

    # Enter some data into the form
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=USER_INPUT,
    )

    # Verify that the flow finishes
    assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
    assert result["title"] == ""

    # Verify that the options were updated

    assert entry.options == USER_INPUT


async def test_config_flow_enabled():
    """Test is manifest.json have 'config_flow': true."""
    path = pathlib.Path.cwd() / "custom_components" / DOMAIN / "manifest.json"
    manifest = json.loads(path.read_text())
    assert manifest.get("config_flow") is True


@pytest.mark.parametrize(*DEFAULT_TEST_SENSORS)
@pytest.mark.parametrize(
    "sensor",
    [
        CONF_INDOOR_TEMPERATURE,
        CONF_INDOOR_HUMIDITY,
        CONF_OUTDOOR_TEMPERATURE,
        CONF_OUTDOOR_HUMIDITY,
    ],
)
async def test_missed_sensors(hass, sensor, start_ha):
    """Test is we show message if sensor missed."""

    result = await _flow_init(hass)

    # Check that the config flow shows the user form as the first step
    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == "user"

    no_sensor = dict(ADVANCED_USER_INPUT)
    no_sensor[sensor] = "foo"
    with pytest.raises(vol.error.MultipleInvalid):
        result = await _flow_configure(hass, result, no_sensor)

    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
