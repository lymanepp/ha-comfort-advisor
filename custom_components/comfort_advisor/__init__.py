"""
Custom integration to integrate comfort_advisor with Home Assistant.

For more details about this integration, please refer to
https://github.com/lymanepp/ha-comfort-advisor
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LOCATION,
    CONF_LONGITUDE,
    CONF_NAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .config_flow import get_value
from .const import (
    CONF_WEATHER_PROVIDER,
    DOMAIN,
    FORECAST_SERVICE,
    PLATFORMS,
    REALTIME_SERVICE,
    SCAN_INTERVAL_FORECAST,
    SCAN_INTERVAL_REALTIME,
    UPDATE_LISTENER,
)
from .sensor import (
    CONF_CUSTOM_ICONS,
    CONF_ENABLED_SENSORS,
    CONF_INDOOR_HUMIDITY_SENSOR,
    CONF_INDOOR_TEMPERATURE_SENSOR,
    CONF_OUTDOOR_HUMIDITY_SENSOR,
    CONF_OUTDOOR_TEMPERATURE_SENSOR,
    CONF_POLL,
    CONF_SCAN_INTERVAL,
)
from .weather_provider import (
    WEATHER_PROVIDERS,
    WeatherData,
    WeatherProviderError,
    load_weather_provider_module,
)

_LOGGER = logging.getLogger(__name__)


class RealtimeDataUpdateCoordinator(DataUpdateCoordinator[WeatherData]):
    """TODO."""


class ForecastDataUpdateCoordinator(DataUpdateCoordinator[list[WeatherData]]):
    """TODO."""


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up entry configured from user interface."""
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = entry_data = {
        CONF_NAME: get_value(entry, CONF_NAME),
        CONF_INDOOR_TEMPERATURE_SENSOR: get_value(
            entry, CONF_INDOOR_TEMPERATURE_SENSOR
        ),
        CONF_INDOOR_HUMIDITY_SENSOR: get_value(entry, CONF_INDOOR_HUMIDITY_SENSOR),
        CONF_OUTDOOR_TEMPERATURE_SENSOR: get_value(
            entry, CONF_OUTDOOR_TEMPERATURE_SENSOR
        ),
        CONF_OUTDOOR_HUMIDITY_SENSOR: get_value(entry, CONF_OUTDOOR_HUMIDITY_SENSOR),
        CONF_POLL: get_value(entry, CONF_POLL),
        CONF_SCAN_INTERVAL: get_value(entry, CONF_SCAN_INTERVAL),
        CONF_CUSTOM_ICONS: get_value(entry, CONF_CUSTOM_ICONS),
    }

    if (enabled_sensors := get_value(entry, CONF_ENABLED_SENSORS)) is not None:
        entry_data[CONF_ENABLED_SENSORS] = enabled_sensors
        data = dict(entry.data)
        data.pop(CONF_ENABLED_SENSORS)
        hass.config_entries.async_update_entry(entry, data=data)

    if entry.unique_id is None:
        # We have no unique_id yet, let's use backup.
        hass.config_entries.async_update_entry(entry, unique_id=entry.entry_id)

    name = entry.data.get(CONF_WEATHER_PROVIDER, "tomorrowio")  # TODO!

    if (provider := WEATHER_PROVIDERS.get(name)) is None:
        await load_weather_provider_module(hass, name)
        if (provider := WEATHER_PROVIDERS.get(name)) is None:
            raise WeatherProviderError(f"Weather provider {'tomorrowio'} was not found")

    weather_provider = provider(
        hass=hass,
        apikey=entry.data[CONF_API_KEY],
        latitude=entry.data[CONF_LOCATION][CONF_LATITUDE],
        longitude=entry.data[CONF_LOCATION][CONF_LONGITUDE],
    )

    realtime_service = RealtimeDataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_{REALTIME_SERVICE}",
        update_interval=SCAN_INTERVAL_REALTIME,
        update_method=weather_provider.realtime,
    )
    await realtime_service.async_config_entry_first_refresh()

    forecast_service = ForecastDataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_{FORECAST_SERVICE}",
        update_interval=SCAN_INTERVAL_FORECAST,
        update_method=weather_provider.forecast,
    )
    await forecast_service.async_config_entry_first_refresh()

    entry_data[REALTIME_SERVICE] = realtime_service
    entry_data[FORECAST_SERVICE] = forecast_service

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)
    update_listener = entry.add_update_listener(async_update_options)
    entry_data[UPDATE_LISTENER] = update_listener
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options from user interface."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove entry via user interface."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        update_listener = hass.data[DOMAIN][entry.entry_id][UPDATE_LISTENER]
        update_listener()
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
