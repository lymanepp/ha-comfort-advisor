"""Custom integration to integrate comfort_advisor with Home Assistant.

For more details about this integration, please refer to
https://github.com/lymanepp/ha-comfort-advisor
"""
from __future__ import annotations

import logging
from typing import Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
import voluptuous as vol

from .const import (
    BINARY_SENSOR_TYPES,
    SENSOR_TYPES,
    DOMAIN,
    SCAN_INTERVAL_FORECAST,
    SCAN_INTERVAL_REALTIME,
    ComfortConfig,
    DeviceConfig,
    InputConfig,
    SectionConfig,
)
from .device import ComfortAdvisorDevice
from .helpers import humidity_sensor_selector, temp_sensor_selector
from .provider import PROVIDER_SCHEMA, WeatherData, provider_from_config

_LOGGER = logging.getLogger(__name__)

PLATFORMS: Final = [Platform.SENSOR, Platform.BINARY_SENSOR]

_INPUTS_SCHEMA = vol.Schema(
    {
        vol.Required(str(InputConfig.INDOOR_TEMPERATURE)): temp_sensor_selector,
        vol.Required(str(InputConfig.INDOOR_HUMIDITY)): humidity_sensor_selector,
        vol.Required(str(InputConfig.OUTDOOR_TEMPERATURE)): temp_sensor_selector,
        vol.Required(str(InputConfig.OUTDOOR_HUMIDITY)): humidity_sensor_selector,
        vol.Optional(str(InputConfig.OUTDOOR_POLLEN)): humidity_sensor_selector,
    }
)

_COMFORT_SCHEMA = vol.Schema(
    {
        vol.Required(str(ComfortConfig.DEWPOINT_MAX)): vol.Coerce(float),
        vol.Required(str(ComfortConfig.SIMMER_INDEX_MAX)): vol.Coerce(float),
        vol.Required(str(ComfortConfig.SIMMER_INDEX_MIN)): vol.Coerce(float),
        vol.Required(str(ComfortConfig.HUMIDITY_MAX)): vol.All(
            vol.Coerce(int), vol.Range(min=90, max=100)
        ),
        vol.Required(str(ComfortConfig.POLLEN_MAX)): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=5)
        ),
    }
)


_DEVICE_SCHEMA = vol.Schema(
    {
        vol.Required(str(DeviceConfig.NAME)): str,
        vol.Required(str(DeviceConfig.ENABLED_SENSORS)): cv.multi_select(
            sorted(BINARY_SENSOR_TYPES + SENSOR_TYPES)
        ),
        vol.Required(str(DeviceConfig.POLL)): vol.Coerce(bool),
        vol.Optional(str(DeviceConfig.POLL_INTERVAL)): vol.All(vol.Coerce(int), vol.Range(min=1)),
    }
)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(str(SectionConfig.PROVIDER)): PROVIDER_SCHEMA,
        vol.Required(str(SectionConfig.INPUTS)): _INPUTS_SCHEMA,
        vol.Required(str(SectionConfig.COMFORT)): _COMFORT_SCHEMA,
        vol.Required(str(SectionConfig.DEVICE)): _DEVICE_SCHEMA,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up entry configured from user interface."""
    hass.data[DOMAIN] = {}
    config = entry.data | entry.options or {}

    if entry.unique_id is None:
        # We have no unique_id yet, let's use backup.
        hass.config_entries.async_update_entry(entry, unique_id=entry.entry_id)

    try:
        DATA_SCHEMA(config)
    except vol.Invalid as exc:
        _LOGGER.error("Invalid configuration: %s", exc)
        return False

    if not (provider := await provider_from_config(hass, config[SectionConfig.PROVIDER])):
        return False

    realtime_service = DataUpdateCoordinator[WeatherData](
        hass,
        _LOGGER,
        name=f"{DOMAIN}_realtime_service",
        update_interval=SCAN_INTERVAL_REALTIME,
        update_method=provider.realtime,
    )

    forecast_service = DataUpdateCoordinator[list[WeatherData]](
        hass,
        _LOGGER,
        name=f"{DOMAIN}_forecast_service",
        update_interval=SCAN_INTERVAL_FORECAST,
        update_method=provider.forecast,
    )

    hass.data[DOMAIN][entry.entry_id] = ComfortAdvisorDevice(
        hass=hass,
        config_entry=entry,
        provider=provider,
        realtime_service=realtime_service,
        forecast_service=forecast_service,
    )

    await realtime_service.async_config_entry_first_refresh()
    await forecast_service.async_config_entry_first_refresh()

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options from user interface."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove entry via user interface."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)  # type: ignore
