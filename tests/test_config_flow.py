"""Tests for the config and options flows."""

from typing import Any

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_NAME,
    CONF_TEMPERATURE_UNIT,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.comfort_advisor.config_flow import _create_unique_id, _validate_inputs
from custom_components.comfort_advisor.const import (
    CONF_ENABLED_SENSORS,
    CONF_INDOOR_HUMIDITY,
    CONF_INDOOR_TEMPERATURE,
    CONF_OUTDOOR_HUMIDITY,
    CONF_OUTDOOR_TEMPERATURE,
    CONF_SIMMER_INDEX_MAX,
    CONF_SIMMER_INDEX_MIN,
    CONF_WEATHER,
    DOMAIN,
)
from custom_components.comfort_advisor.schemas import _forecast_has_humidity, build_comfort_schema

from .conftest import (
    COMFORT,
    ENTRY_DATA,
    INDOOR_HUMIDITY,
    INPUTS,
    OUTDOOR_HUMIDITY,
    OUTDOOR_TEMPERATURE,
    WEATHER_ENTITY,
    MockWeather,
)

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
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
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


def test_validate_inputs_valid(hass: HomeAssistant):
    """The test inputs are valid."""
    assert _validate_inputs(hass, INPUTS) == {}


def test_validate_inputs_missing_entity(hass: HomeAssistant):
    """An entity that no longer exists is reported on its field.

    The entity selectors only offer existing entities, but one can disappear
    between showing the form and submitting it.
    """
    hass.states.async_remove(INDOOR_HUMIDITY)
    assert _validate_inputs(hass, INPUTS) == {CONF_INDOOR_HUMIDITY: "entity_not_found"}


def test_validate_inputs_missing_weather(hass: HomeAssistant):
    """A weather entity that no longer exists is reported on its field."""
    assert _validate_inputs(hass, INPUTS | {CONF_WEATHER: "weather.gone"}) == {
        CONF_WEATHER: "entity_not_found"
    }


def test_validate_inputs_wrong_units(hass: HomeAssistant):
    """A sensor whose unit changed to an unusable one is reported on its field."""
    hass.states.async_set(
        OUTDOOR_HUMIDITY, "10", {ATTR_UNIT_OF_MEASUREMENT: "g/m³", ATTR_DEVICE_CLASS: "humidity"}
    )
    assert _validate_inputs(hass, INPUTS) == {CONF_OUTDOOR_HUMIDITY: "invalid_units"}


def test_validate_inputs_fahrenheit_is_valid(hass: HomeAssistant):
    """Temperature sensors in °F are accepted."""
    hass.states.async_set(
        OUTDOOR_TEMPERATURE,
        "72",
        {ATTR_UNIT_OF_MEASUREMENT: "°F", ATTR_DEVICE_CLASS: "temperature"},
    )
    assert _validate_inputs(hass, INPUTS) == {}


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({}, True),
        ({"samples": []}, False),
        ({"fail": True}, False),
        ({"include_humidity": False}, False),
    ],
)
async def test_forecast_has_humidity(
    hass: HomeAssistant, weather: MockWeather, change: dict, expected: bool
):
    """Weather entities are offered only if their hourly forecast has humidity.

    An empty forecast or a failing provider must not break the config flow.
    """
    for attr, value in change.items():
        setattr(weather, attr, value)
    assert await _forecast_has_humidity(hass, WEATHER_ENTITY) is expected


async def test_user_flow_with_failing_weather_provider(hass: HomeAssistant, weather: MockWeather):
    """The form still opens when the weather provider fails."""
    weather.fail = True
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


def add_other_sensors(hass: HomeAssistant) -> dict[str, str]:
    """Create a second set of indoor sensors; return them as inputs."""
    hass.states.async_set(
        "sensor.bedroom_temperature",
        "23",
        {ATTR_UNIT_OF_MEASUREMENT: "°C", ATTR_DEVICE_CLASS: "temperature"},
    )
    hass.states.async_set(
        "sensor.bedroom_humidity",
        "45",
        {ATTR_UNIT_OF_MEASUREMENT: "%", ATTR_DEVICE_CLASS: "humidity"},
    )
    return INPUTS | {
        CONF_INDOOR_TEMPERATURE: "sensor.bedroom_temperature",
        CONF_INDOOR_HUMIDITY: "sensor.bedroom_humidity",
    }


async def test_reconfigure(hass: HomeAssistant):
    """The sensors can be changed; the unique ID and other settings are kept."""
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id="test")
    entry.add_to_hass(hass)
    new_inputs = add_other_sensors(hass)

    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], new_inputs)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_INDOOR_TEMPERATURE] == "sensor.bedroom_temperature"
    assert entry.data[CONF_INDOOR_HUMIDITY] == "sensor.bedroom_humidity"
    assert entry.data[CONF_SIMMER_INDEX_MAX] == ENTRY_DATA[CONF_SIMMER_INDEX_MAX]
    assert entry.unique_id == "test"


async def test_reconfigure_validates_inputs(hass: HomeAssistant):
    """Reconfigure reports the same errors as the user flow."""
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id="test")
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], INPUTS | {CONF_OUTDOOR_HUMIDITY: INPUTS[CONF_INDOOR_HUMIDITY]}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "sensors_not_unique"}
    assert entry.data == ENTRY_DATA


async def test_reconfigure_rejects_inputs_of_another_entry(hass: HomeAssistant):
    """Reconfigure can't switch to inputs another entry already uses."""
    new_inputs = add_other_sensors(hass)
    other = MockConfigEntry(
        domain=DOMAIN,
        data=ENTRY_DATA | new_inputs,
        unique_id=_create_unique_id(hass, new_inputs),
    )
    other.add_to_hass(hass)
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id="test")
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], new_inputs)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data == ENTRY_DATA


def comfort_form_defaults(hass: HomeAssistant) -> dict[str, Any]:
    """Return the default values shown on a new entry's comfort form."""
    schema = build_comfort_schema(hass, {})
    return {str(key): key.default() for key in schema.schema}


async def test_comfort_form_defaults_fahrenheit(hass: HomeAssistant):
    """The comfort form starts with the documented defaults in °F."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    assert comfort_form_defaults(hass) == {
        "simmer_index_min": 70.0,
        "simmer_index_max": 85.0,
        "dew_point_max": 60.0,
        "humidity_max": 95,
        "pollen_max": 2,
        "cooling_temperature_min": 60.0,
        "temperature_tolerance": 2.0,
        "hysteresis": 1.0,
        "humidity_hysteresis": 2,
    }


async def test_comfort_form_defaults_celsius(hass: HomeAssistant):
    """In °C, temperatures are converted as values and margins as differences."""
    hass.config.units = METRIC_SYSTEM
    assert comfort_form_defaults(hass) == {
        "simmer_index_min": 21.1,
        "simmer_index_max": 29.4,
        "dew_point_max": 15.6,
        "humidity_max": 95,
        "pollen_max": 2,
        "cooling_temperature_min": 15.6,
        "temperature_tolerance": 1.11,
        "hysteresis": 0.56,
        "humidity_hysteresis": 2,
    }


async def test_user_flow_rejects_reversed_simmer_index_range(hass: HomeAssistant):
    """The lowest comfortable simmer index must be below the highest."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], INPUTS)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], COMFORT | {CONF_SIMMER_INDEX_MIN: 30.0, CONF_SIMMER_INDEX_MAX: 25.0}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "comfort"
    assert result["errors"] == {CONF_SIMMER_INDEX_MAX: "simmer_index_range"}


async def test_options_flow_rejects_reversed_simmer_index_range(hass: HomeAssistant):
    """The options flow checks the simmer index range too."""
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id="test")
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], COMFORT | {CONF_SIMMER_INDEX_MIN: 29.5, CONF_SIMMER_INDEX_MAX: 29.5}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    assert result["errors"] == {CONF_SIMMER_INDEX_MAX: "simmer_index_range"}
