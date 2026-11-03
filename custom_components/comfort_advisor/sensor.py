"""Sensor platform for comfort_advisor."""

from enum import StrEnum
from typing import cast

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .comfort import Calculated
from .const import _LOGGER, CONF_ENABLED_SENSORS, DOMAIN
from .device import ComfortAdvisorConfigEntry, ComfortAdvisorDevice


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ComfortAdvisorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up entity configured via user interface."""
    config = config_entry.data | config_entry.options
    device = config_entry.runtime_data

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

    async_add_entities(sensors)


class ComfortAdvisorSensor(SensorEntity):
    """Representation of a Comfort Advisor Sensor."""

    _attr_has_entity_name = True
    _attr_should_poll = False

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
        self.entity_description = entity_description
        self._attr_translation_key = entity_description.key
        self._attr_device_info = device.device_info
        self._attr_entity_registry_enabled_default = enabled_default
        if device.unique_id:
            self._attr_unique_id = f"{device.unique_id}_{entity_description.key}"
        if entity_description.device_class == SensorDeviceClass.TEMPERATURE:
            self._attr_native_unit_of_measurement = hass.config.units.temperature_unit

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        self.async_on_remove(self._device.add_entity(self))
        self.async_schedule_update_ha_state(force_refresh=True)

    @property
    def available(self) -> bool:
        """Unavailable while any input is unavailable."""
        return self._device.available

    async def async_update(self) -> None:
        """Update the state of the sensor."""
        value = self._device.get_calculated(self.entity_description.key)
        _LOGGER.debug("async_update called for %s - state(%s)", self.entity_id, str(value))
        self._attr_native_value = value
        if self.entity_description.key == Calculated.CAN_OPEN_WINDOWS:
            self._attr_extra_state_attributes = dict(self._device.extra_attributes)


class ComfortAdvisorDeviceClass(StrEnum):
    """Device class for comfort advisor sensors."""

    CAN_OPEN_WINDOWS = f"{DOMAIN}__{Calculated.CAN_OPEN_WINDOWS}"


SENSOR_DESCRIPTIONS = [
    SensorEntityDescription(
        key=Calculated.AVERAGE_TEMPERATURE,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key=Calculated.ENTHALPY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="kJ/kg",
    ),
    SensorEntityDescription(
        key=Calculated.SIMMER_INDEX,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
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
    SensorEntityDescription(
        key=Calculated.HIGH_ENTHALPY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="kJ/kg",
    ),
    SensorEntityDescription(
        key=Calculated.LOW_ENTHALPY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="kJ/kg",
    ),
]
