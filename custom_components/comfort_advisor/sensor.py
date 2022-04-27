"""Sensor platform for comfort_advisor."""
from __future__ import annotations

import logging

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

from .const import CONF_ENABLED_SENSORS, DOMAIN
from .device import ComfortAdvisorDevice

_LOGGER = logging.getLogger(__name__)


class ComfortAdvisorSensor(SensorEntity):
    """Representation of a Comfort Advisor Sensor."""

    def __init__(
        self,
        *,
        device: ComfortAdvisorDevice,
        entity_description: SensorEntityDescription,
        sensor_type: SensorType,
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
        self._attr_native_value = None
        self._attr_extra_state_attributes = dict(device.extra_state_attributes)
        self._attr_should_poll = False
        if device.unique_id:
            self._attr_unique_id = f"{device.unique_id}_{sensor_type}"

    async def async_added_to_hass(self):
        """Run when entity about to be added to hass."""
        self._device.sensors.append(self)
        # self.async_schedule_update_ha_state(True)

        # TODO: schedule first update?
        # if self._device.get_compute_state(self._sensor_type).needs_update:
        #    self.async_schedule_update_ha_state(True)

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        self._device.sensors.remove(self)

    async def async_update(self):
        """Update the state of the sensor."""
        self._attr_native_value = getattr(self._device, self.entity_description.key)


class SensorType(StrEnum):
    """Sensor type enum."""

    OPEN_WINDOWS_REASON = "open_windows_reason"


class ComfortAdvisorDeviceClass(StrEnum):
    """State class for comfort advisor sensors."""

    OPEN_WINDOWS_REASON = "comfort_advisor__open_windows_reason"


SENSOR_DESCRIPTIONS: list[SensorEntityDescription] = [
    SensorEntityDescription(
        key=SensorType.OPEN_WINDOWS_REASON,
        icon="mdi:water",
        state_class=ComfortAdvisorDeviceClass.OPEN_WINDOWS_REASON,
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

    entities: list[ComfortAdvisorSensor] = [
        ComfortAdvisorSensor(
            device=device,
            entity_description=entity_description,
            sensor_type=entity_description.key,
        )
        for entity_description in SENSOR_DESCRIPTIONS
    ]

    if enabled_sensors := config.get(CONF_ENABLED_SENSORS):
        for entity in entities:
            if entity.entity_description.key not in enabled_sensors:
                entity.entity_description.entity_registry_enabled_default = False

    if entities:
        async_add_entities(entities)
