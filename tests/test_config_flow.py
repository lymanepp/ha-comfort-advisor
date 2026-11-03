"""Tests for the config and options flows."""


from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_NAME, CONF_TEMPERATURE_UNIT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.comfort_advisor.const import (
    CONF_ENABLED_SENSORS,
    CONF_INDOOR_TEMPERATURE,
    CONF_OUTDOOR_TEMPERATURE,
    CONF_SIMMER_INDEX_MAX,
    DOMAIN,
)

from .conftest import COMFORT, ENTRY_DATA, INPUTS

pytestmark = pytest.mark.usefixtures("weather", "sensors")


@pytest.fixture(autouse=True)
def skip_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Don't set up the entry once the flow creates it."""

    async def _setup(*_):
        return True

    monkeypatch.setattr("custom_components.comfort_advisor.async_setup_entry", _setup)


async def test_user_flow(hass: HomeAssistant):
    """The three-step flow creates an entry with all settings."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["description_placeholders"]["blueprint_url"].startswith("https://")

    result = await hass.config_entries.flow.async_configure(result["flow_id"], INPUTS)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "comfort"
    # simmer index guide values are converted to the system unit (70°F == 21.1°C)
    assert result["description_placeholders"]["ssi_70"] == "21.1"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], COMFORT)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "device"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Living Room", CONF_ENABLED_SENSORS: ["can_open_windows"]},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Living Room"
    assert result["data"] == {
        **INPUTS,
        **COMFORT,
        CONF_TEMPERATURE_UNIT: "°C",
        CONF_NAME: "Living Room",
        CONF_ENABLED_SENSORS: ["can_open_windows"],
    }
    assert result["result"].unique_id


async def test_user_flow_rejects_same_indoor_and_outdoor_sensor(hass: HomeAssistant):
    """Indoor and outdoor sensors must differ."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        INPUTS | {CONF_OUTDOOR_TEMPERATURE: INPUTS[CONF_INDOOR_TEMPERATURE]},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "sensors_not_unique"}


async def test_user_flow_aborts_for_duplicate_inputs(hass: HomeAssistant):
    """The same set of inputs can only be configured once."""
    for expected in (FlowResultType.FORM, FlowResultType.ABORT):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], INPUTS)
        assert result["type"] is expected
        if expected is FlowResultType.FORM:
            result = await hass.config_entries.flow.async_configure(result["flow_id"], COMFORT)
            await hass.config_entries.flow.async_configure(
                result["flow_id"], {CONF_NAME: "First", CONF_ENABLED_SENSORS: []}
            )
    assert result["reason"] == "already_configured"


async def test_options_flow(hass: HomeAssistant):
    """Comfort and device settings can be changed later."""
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id="test")
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], COMFORT | {CONF_SIMMER_INDEX_MAX: 28.0}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "device"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_NAME: "Renamed", CONF_ENABLED_SENSORS: ["enthalpy"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SIMMER_INDEX_MAX] == 28.0
    assert entry.options[CONF_NAME] == "Renamed"
    assert entry.options[CONF_ENABLED_SENSORS] == ["enthalpy"]
