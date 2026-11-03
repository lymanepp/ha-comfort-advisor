"""Helper functions."""

from collections.abc import Callable, Iterable
from typing import Literal

from homeassistant.components.weather.const import DATA_COMPONENT as WEATHER_COMPONENT
from homeassistant.const import ATTR_DEVICE_CLASS, ATTR_SUPPORTED_FEATURES, ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import device_registry, entity_registry
from homeassistant.util.json import JsonValueType

from .const import DOMAIN

EXCLUDED_PLATFORMS = (DOMAIN, "thermal_comfort")


async def async_subscribe_forecast(
    hass: HomeAssistant,
    entity_id: str,
    forecast_type: Literal["daily", "hourly", "twice_daily"],
    forecast_listener: Callable[[list[JsonValueType] | None], None],
) -> CALLBACK_TYPE | None:
    """Subscribe to forecast updates.

    This should be in HA Core!
    """

    component = hass.data.get(WEATHER_COMPONENT)
    weather_entity = component.get_entity(entity_id) if component else None
    if weather_entity is None:
        return None

    unsubscribe = weather_entity.async_subscribe_forecast(forecast_type, forecast_listener)

    # Push an initial forecast update
    await weather_entity.async_update_listeners([forecast_type])

    return unsubscribe


def domain_entity_ids(
    hass: HomeAssistant,
    domains: str | Iterable[str],
    device_classes: str | Iterable[str] | None = None,
    units_of_measurement: str | Iterable[str] | None = None,
    required_features: int | None = None,
) -> list[str]:
    """Get list of matching entities."""

    if isinstance(domains, str):
        domains = [domains]

    if isinstance(device_classes, str):
        device_classes = [device_classes]

    if isinstance(units_of_measurement, str):
        units_of_measurement = [units_of_measurement]

    ent_reg = entity_registry.async_get(hass)

    ignore_ids = [
        entity.entity_id
        for entity in list(ent_reg.entities.values())
        if entity.platform in EXCLUDED_PLATFORMS
    ]

    entity_ids = []

    for state in hass.states.async_all(domains):
        if state.entity_id in ignore_ids:
            continue

        if device_classes:
            device_class = state.attributes.get(ATTR_DEVICE_CLASS)
            if not device_class or device_class not in device_classes:
                continue

        if units_of_measurement:
            unit_of_measurement = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
            if not unit_of_measurement or unit_of_measurement not in units_of_measurement:
                continue

        if required_features:
            supported_features = state.attributes.get(ATTR_SUPPORTED_FEATURES, 0)
            if (supported_features & required_features) != required_features:
                continue

        entity = ent_reg.async_get(state.entity_id)
        if entity and entity.hidden:
            continue

        entity_ids.append(state.entity_id)

    return entity_ids


def get_entity_area(hass: HomeAssistant, entity_id: str) -> str | None:
    """Get the area of an entity (if one is assigned)."""
    ent_reg = entity_registry.async_get(hass)
    entity = ent_reg.async_get(entity_id)
    if entity:
        if entity.area_id:
            return entity.area_id

        if entity.device_id:
            dev_reg = device_registry.async_get(hass)
            device = dev_reg.async_get(entity.device_id)
            if device and device.area_id:
                return device.area_id

    return None
