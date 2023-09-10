"""Sensor platform for comfort_advisor."""
from __future__ import annotations

from typing import cast

from homeassistant.backports.enum import StrEnum
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .comfort import Calculated
from .const import _LOGGER, CONF_ENABLED_SENSORS, DOMAIN
from .device import ComfortAdvisorDevice


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up entity configured via user interface."""
    config = config_entry.data | config_entry.options or {}
    device: ComfortAdvisorDevice = hass.data[DOMAIN][config_entry.entry_id]

    _LOGGER.debug("async_setup_entry: %s", config_entry.title)

    enabled_sensors = config[CONF_ENABLED_SENSORS]

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

        sensor_name = entity_description.key.replace("_", " ").title()

        self._attr_name = f"{device.name} {sensor_name}"
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
        self.async_schedule_update_ha_state(force_refresh=True)

    async def async_update(self) -> None:
        """Update the state of the sensor."""
        value = self._device.get_calculated(self.entity_description.key)
        _LOGGER.debug("async_update called for %s - state(%s)", self.entity_id, str(value))
        self._attr_native_value = value


class ComfortAdvisorDeviceClass(StrEnum):  # type: ignore
    """Device class for comfort advisor sensors."""

    CAN_OPEN_WINDOWS = f"{DOMAIN}__{Calculated.CAN_OPEN_WINDOWS}"


SENSOR_DESCRIPTIONS = [
    SensorEntityDescription(
        key=Calculated.CAN_OPEN_WINDOWS,
        device_class=cast(SensorDeviceClass, ComfortAdvisorDeviceClass.CAN_OPEN_WINDOWS),
        icon="mdi:window-closed",
    ),
    SensorEntityDescription(
        key=Calculated.OPEN_WINDOWS_AT,
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key=Calculated.CLOSE_WINDOWS_AT,
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key=Calculated.HIGH_SIMMER_INDEX,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key=Calculated.LOW_SIMMER_INDEX,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
]
