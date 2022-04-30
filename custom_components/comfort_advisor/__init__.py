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

from .config_flow import humidity_sensor_selector, temp_sensor_selector  # TODO!
from .const import (
    DOMAIN,
    SCAN_INTERVAL_FORECAST,
    SCAN_INTERVAL_REALTIME,
    SENSOR_TYPES,
    ConfigValue,
)
from .device import ComfortAdvisorDevice
from .provider import (
    SCHEMA as PROVIDER_SCHEMA,
    ProviderError,
    WeatherData,
    create_provider_from_config,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: Final = [Platform.SENSOR, Platform.BINARY_SENSOR]

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(str(ConfigValue.PROVIDER)): PROVIDER_SCHEMA,
        vol.Required(str(ConfigValue.IN_TEMP_SENSOR)): temp_sensor_selector,
        vol.Required(str(ConfigValue.IN_HUMIDITY_SENSOR)): humidity_sensor_selector,
        vol.Required(str(ConfigValue.OUT_TEMP_SENSOR)): temp_sensor_selector,
        vol.Required(str(ConfigValue.OUT_HUMIDITY_SENSOR)): humidity_sensor_selector,
        vol.Required(str(ConfigValue.NAME)): str,
        vol.Required(str(ConfigValue.DEWPOINT_MAX)): vol.Coerce(float),
        vol.Required(str(ConfigValue.SIMMER_INDEX_MAX)): vol.Coerce(float),
        vol.Required(str(ConfigValue.SIMMER_INDEX_MIN)): vol.Coerce(float),
        vol.Required(str(ConfigValue.HUMIDITY_MAX)): vol.All(
            vol.Coerce(int), vol.Range(min=90, max=100)
        ),
        vol.Required(str(ConfigValue.POLLEN_MAX)): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=5)
        ),
        vol.Required(str(ConfigValue.ENABLED_SENSORS)): cv.multi_select(SENSOR_TYPES),
        vol.Required(str(ConfigValue.POLL)): bool,
        vol.Optional(str(ConfigValue.POLL_INTERVAL)): vol.All(  # TODO: required if "poll" is True
            vol.Coerce(int), vol.Range(min=1)
        ),
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

    try:
        provider = await create_provider_from_config(hass, config[ConfigValue.PROVIDER])
    except ProviderError as exc:
        _LOGGER.error(
            "Weather provider didn't load: %s, %s, %s", exc, exc.error_key, exc.extra_info
        )
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

    device = ComfortAdvisorDevice(
        hass=hass,
        config_entry=entry,
        provider=provider,
        realtime_service=realtime_service,
        forecast_service=forecast_service,
    )

    hass.data[DOMAIN][entry.entry_id] = device

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
