"""Sensor platform for comfort_advisor."""
from __future__ import annotations

import logging
from typing import Any, Mapping

from homeassistant.backports.enum import StrEnum
from homeassistant.components.sensor import (
    DOMAIN as SENSOR_DOMAIN,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, ConfigValue
from .device import ComfortAdvisorDevice, DeviceState

_LOGGER = logging.getLogger(__name__)


class ComfortAdvisorSensor(SensorEntity):  # type: ignore
    """Representation of a Comfort Advisor Sensor."""

    def __init__(
        self,
        *,
        device: ComfortAdvisorDevice,
        entity_description: SensorEntityDescription,
        sensor_type: str,
    ) -> None:
        """Initialize the sensor."""
        self._device = device
        self.entity_description = entity_description

        friendly_name = sensor_type.replace("_", " ").title()

        self.entity_id = async_generate_entity_id(
            SENSOR_DOMAIN + ".{}",
            f"{device.name}_{sensor_type}",
            hass=device.hass,
        )

        self._attr_name = f"{device.name} {friendly_name}"
        self._attr_device_info = device.device_info
        self._attr_should_poll = False
        if device.unique_id:
            self._attr_unique_id = f"{device.unique_id}_{sensor_type}"

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return device state attributes."""
        return self._device.extra_state_attributes

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        self.async_on_remove(self._device.add_entity(self))
        self.async_schedule_update_ha_state(True)

    async def async_update(self) -> None:
        """Update the state of the sensor."""
        if (value := self._device.states[self.entity_description.key]) is not None:
            self._attr_native_value = value


class ComfortAdvisorDeviceClass(StrEnum):  # type: ignore
    """State class for comfort advisor sensors."""

    OPEN_WINDOWS_REASON = f"{DOMAIN}__{DeviceState.OPEN_WINDOWS_REASON}"


SENSOR_DESCRIPTIONS = [
    SensorEntityDescription(
        key=DeviceState.OPEN_WINDOWS_REASON,
        icon="mdi:water",
        device_class=ComfortAdvisorDeviceClass.OPEN_WINDOWS_REASON,
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

    sensors = [
        ComfortAdvisorSensor(
            device=device,
            entity_description=entity_description,
            sensor_type=entity_description.key,
        )
        for entity_description in SENSOR_DESCRIPTIONS
    ]

    if enabled_sensors := config.get(ConfigValue.ENABLED_SENSORS):
        for entity in sensors:
            if entity.entity_description.key not in enabled_sensors:
                entity.entity_description.entity_registry_enabled_default = False

    if sensors:
        async_add_entities(sensors)
