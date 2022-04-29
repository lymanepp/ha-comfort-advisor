"""Sensor platform for comfort_advisor."""
from __future__ import annotations

import logging

from homeassistant.backports.enum import StrEnum
from homeassistant.components.binary_sensor import (
    DOMAIN as BINARY_SENSOR_DOMAIN,
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, ConfigValue
from .device import ComfortAdvisorDevice

_LOGGER = logging.getLogger(__name__)


class ComfortAdvisorBinarySensor(BinarySensorEntity):
    """Representation of a Comfort Advisor binary sensor."""

    def __init__(
        self,
        *,
        device: ComfortAdvisorDevice,
        entity_description: BinarySensorEntityDescription,
        sensor_type: BinarySensorType,
    ) -> None:
        """Initialize the sensor."""
        self._device = device
        self.entity_description = entity_description

        friendly_name = sensor_type.replace("_", " ").title()

        self.entity_id = async_generate_entity_id(
            BINARY_SENSOR_DOMAIN + ".{}",
            f"{device.name}_{sensor_type}",
            hass=device.hass,
        )

        self._attr_name = f"{device.name} {friendly_name}"
        self._attr_device_info = device.device_info
        self._attr_native_value = None
        self._attr_extra_state_attributes = dict(device.extra_state_attributes)
        self._attr_should_poll = False
        if device.unique_id:
            self._attr_unique_id = f"{device.unique_id}_{sensor_type}"

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        self._device.sensors.append(self)
        # self.async_schedule_update_ha_state(True)

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        self._device.sensors.remove(self)

    async def async_update(self) -> None:
        """Update the state of the sensor."""
        self._attr_is_on = getattr(self._device, self.entity_description.key)
        self._attr_extra_state_attributes = self._device.extra_state_attributes


class BinarySensorType(StrEnum):
    """Binary Sensor type enum."""

    OPEN_WINDOWS = "open_windows"


BINARY_SENSOR_DESCRIPTIONS = [
    BinarySensorEntityDescription(
        key=BinarySensorType.OPEN_WINDOWS,
        device_class=BinarySensorDeviceClass.WINDOW,
        icon="mdi:window",
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up entity configured via user interface."""
    config = config_entry.data | config_entry.options or {}
    device = hass.data[DOMAIN][config_entry.entry_id]

    _LOGGER.debug("async_setup_entry: %s", config_entry)

    entities = [
        ComfortAdvisorBinarySensor(
            device=device,
            entity_description=entity_description,
            sensor_type=entity_description.key,
        )
        for entity_description in BINARY_SENSOR_DESCRIPTIONS
    ]

    if enabled_sensors := config.get(ConfigValue.ENABLED_SENSORS):
        for entity in entities:
            if entity.entity_description.key not in enabled_sensors:
                entity.entity_description.entity_registry_enabled_default = False

    if entities:
        async_add_entities(entities)
