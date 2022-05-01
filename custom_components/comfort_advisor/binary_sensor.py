"""Sensor platform for comfort_advisor."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    DOMAIN as BINARY_SENSOR_DOMAIN,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import BINARY_SENSOR_DESCRIPTIONS, BINARY_SENSOR_TYPES, DOMAIN, DeviceConfig
from .device import ComfortAdvisorDevice

_LOGGER = logging.getLogger(__name__)


class ComfortAdvisorBinarySensor(BinarySensorEntity):  # type: ignore
    """Representation of a Comfort Advisor binary sensor."""

    def __init__(
        self,
        *,
        device: ComfortAdvisorDevice,
        entity_description: BinarySensorEntityDescription,
        enabled_default: bool = False,
    ) -> None:
        """Initialize the sensor."""
        self._device = device

        # TODO: translation support?
        friendly_name = entity_description.key.replace("_", " ").title()

        self._attr_name = f"{device.name} {friendly_name}"
        self._attr_device_info = device.device_info
        self.entity_description = entity_description
        self.entity_id = async_generate_entity_id(
            BINARY_SENSOR_DOMAIN + ".{}",
            f"{device.name}_{entity_description.key}",
            hass=device.hass,
        )
        self._attr_entity_registry_enabled_default = enabled_default
        self._attr_should_poll = False
        if device.unique_id:
            self._attr_unique_id = f"{device.unique_id}_{entity_description.key}"

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        self.async_on_remove(self._device.add_entity(self))
        self.async_schedule_update_ha_state(True)

    async def async_update(self) -> None:
        """Update the state of the sensor."""
        if (value := self._device.state.get(self.entity_description.key)) is not None:
            self._attr_is_on = value
            self._attr_extra_state_attributes = self._device.extra_state_attributes


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up entity configured via user interface."""
    config: dict[str, Any] = config_entry.data | config_entry.options or {}
    device: ComfortAdvisorDevice = hass.data[DOMAIN][config_entry.entry_id]

    _LOGGER.debug("async_setup_entry: %s", config_entry)

    enabled_sensors = config.get(DeviceConfig.ENABLED_SENSORS, BINARY_SENSOR_TYPES)

    sensors = [
        ComfortAdvisorBinarySensor(
            device=device,
            entity_description=entity_description,
            enabled_default=entity_description.key in enabled_sensors,
        )
        for entity_description in BINARY_SENSOR_DESCRIPTIONS
    ]

    if sensors:
        async_add_entities(sensors)
