"""Sensor platform for comfort_advisor."""
from __future__ import annotations

import logging
from typing import Any, Mapping

from homeassistant.components.sensor import (
    DOMAIN as SENSOR_DOMAIN,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_DEVICE,
    CONF_ENABLED_SENSORS,
    DOMAIN,
    STATE_HIGH_SIMMER_INDEX,
    STATE_NEXT_CHANGE_TIME,
)
from .device import ComfortAdvisorDevice

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up entity configured via user interface."""
    config: Mapping[str, Any] = config_entry.data | config_entry.options or {}
    device: ComfortAdvisorDevice = hass.data[DOMAIN][config_entry.entry_id]

    _LOGGER.debug("async_setup_entry: %s", config_entry.title)

    enabled_sensors = config[CONF_DEVICE][CONF_ENABLED_SENSORS]

    sensors = [
        ComfortAdvisorSensor(
            hass=hass,
            device=device,
            entity_description=entity_description,
            enabled_default=entity_description.key in enabled_sensors,
        )
        for entity_description in SENSOR_DESCRIPTIONS
    ]

    if sensors:
        async_add_entities(sensors)


class ComfortAdvisorSensor(SensorEntity):  # type: ignore
    """Representation of a Comfort Advisor Sensor."""

    def __init__(
        self,
        *,
        hass: HomeAssistant,
        device: ComfortAdvisorDevice,
        entity_description: SensorEntityDescription,
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
            SENSOR_DOMAIN + ".{}",
            f"{device.name}_{entity_description.key}",
            hass=hass,
        )
        self._attr_entity_registry_enabled_default = enabled_default
        self._attr_should_poll = False
        if device.unique_id:
            self._attr_unique_id = f"{device.unique_id}_{entity_description.key}"
        if entity_description.device_class == SensorDeviceClass.TEMPERATURE:
            entity_description.native_unit_of_measurement = hass.config.units.temperature_unit

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        self.async_on_remove(self._device.add_entity(self))

    async def async_update(self) -> None:
        """Update the state of the sensor."""
        _LOGGER.debug(
            "async_update called for %s - state(%s)",
            self.entity_id,
            str(self._device.calculated.get(self.entity_description.key)),
        )
        if (value := self._device.calculated.get(self.entity_description.key)) is not None:
            self._attr_native_value = value
            self._attr_extra_state_attributes = self._device.extra_state_attributes


SENSOR_DESCRIPTIONS = [
    SensorEntityDescription(
        key=STATE_NEXT_CHANGE_TIME,
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key=STATE_HIGH_SIMMER_INDEX,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
]
