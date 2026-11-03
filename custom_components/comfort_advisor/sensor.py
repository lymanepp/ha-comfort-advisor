"""Sensor platform for comfort_advisor."""

from datetime import datetime
from typing import cast

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .comfort import Calculated
from .const import _LOGGER, CONF_ENABLED_SENSORS, OUTPUT_PRECISION
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
        if entity_description.device_class in (
            SensorDeviceClass.TEMPERATURE,
            SensorDeviceClass.TEMPERATURE_DELTA,
        ):
            self._attr_native_unit_of_measurement = hass.config.units.temperature_unit

    async def async_added_to_hass(self) -> None:
        """Write the state whenever the calculated values change."""
        self.async_on_remove(self._device.async_add_listener(self.async_write_ha_state))

    @property
    def available(self) -> bool:
        """Unavailable while any input is unavailable."""
        return self._device.available

    @property
    def native_value(self) -> StateType | datetime:
        """Return the calculated value."""
        return cast(StateType | datetime, self._device.get_calculated(self.entity_description.key))


SENSOR_DESCRIPTIONS = [
    SensorEntityDescription(
        key=Calculated.AVERAGE_TEMPERATURE,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=OUTPUT_PRECISION,
    ),
    SensorEntityDescription(
        key=Calculated.ENTHALPY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=OUTPUT_PRECISION,
        native_unit_of_measurement="kJ/kg",
    ),
    SensorEntityDescription(
        key=Calculated.SIMMER_INDEX,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=OUTPUT_PRECISION,
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
        suggested_display_precision=OUTPUT_PRECISION,
    ),
    SensorEntityDescription(
        key=Calculated.LOW_SIMMER_INDEX,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=OUTPUT_PRECISION,
    ),
    SensorEntityDescription(
        key=Calculated.HIGH_ENTHALPY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=OUTPUT_PRECISION,
        native_unit_of_measurement="kJ/kg",
    ),
    SensorEntityDescription(
        key=Calculated.LOW_ENTHALPY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=OUTPUT_PRECISION,
        native_unit_of_measurement="kJ/kg",
    ),
    SensorEntityDescription(
        key=Calculated.FORECAST_TEMPERATURE_OFFSET,
        device_class=SensorDeviceClass.TEMPERATURE_DELTA,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=OUTPUT_PRECISION,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=Calculated.FORECAST_DEW_POINT_OFFSET,
        device_class=SensorDeviceClass.TEMPERATURE_DELTA,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=OUTPUT_PRECISION,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
]
