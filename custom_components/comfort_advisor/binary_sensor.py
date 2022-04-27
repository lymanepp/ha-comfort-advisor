"""Sensor platform for comfort_advisor."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import takewhile
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
from homeassistant.util.temperature import convert as convert_temp

from benchmark import TEMP_FAHRENHEIT

from .const import CONF_ENABLED_SENSORS, DOMAIN
from .device import ComfortAdvisorDevice
from .formulas import dew_point, simmer_index

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

    async def async_added_to_hass(self):
        """Run when entity about to be added to hass."""
        self._device.sensors.append(self)
        # self.async_schedule_update_ha_state(True)

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        self._device.sensors.remove(self)

    async def async_update(self):
        """Update the state of the sensor."""
        pass
        # TODO
        # self._attr_native_value = False


class OpenWindowsBinarySensor(ComfortAdvisorBinarySensor):
    """TODO."""

    def __init__(self, **kwargs) -> None:
        """TODO."""
        super().__init__(**kwargs)

        self.temp_unit = self.hass.config.units.temperature_unit

        # these need to come from configuration
        self.dewp_comfort_max = convert_temp(60, TEMP_FAHRENHEIT, self.temp_unit)
        self.ssi_comfort_min = convert_temp(77, TEMP_FAHRENHEIT, self.temp_unit)
        self.ssi_comfort_max = convert_temp(83, TEMP_FAHRENHEIT, self.temp_unit)
        self.rh_max = 97.0

    async def async_update(self):
        """Update the state of the sensor."""

        def is_comfortable(dewp: float, ssi: float, rel_hum: float) -> bool:
            return (
                rel_hum <= self.rh_max
                and ssi <= self.ssi_comfort_max
                and dewp <= self.dewp_comfort_max
            )

        state = self._device._state

        indoor_dewp = dew_point(
            state.indoor_temp, state.indoor_humidity, self.temp_unit
        )
        indoor_ssi = simmer_index(
            state.indoor_temp, state.indoor_humidity, self.temp_unit
        )
        outdoor_dewp = dew_point(
            state.outdoor_temp, state.outdoor_humidity, self.temp_unit
        )
        outdoor_ssi = simmer_index(
            state.outdoor_temp, state.outdoor_humidity, self.temp_unit
        )
        outdoor_comfort = is_comfortable(
            outdoor_dewp, outdoor_ssi, state.outdoor_humidity
        )

        hourly_comfort: list[bool] = []
        hourly_ssi: list[float] = []

        for data in state.forecast:
            dewp = dew_point(data.temp, data.humidity, self.temp_unit)
            ssi = simmer_index(data.temp, data.humidity, self.temp_unit)
            hourly_comfort.append(is_comfortable(dewp, ssi, data.humidity))
            hourly_ssi.append(ssi)

        reason = (
            "more_comfortable_indoors"
            if outdoor_ssi > indoor_ssi or outdoor_dewp > indoor_dewp
            else "outdoor_ssi_too_high"
            if outdoor_ssi > self.ssi_comfort_max
            else "outdoor_dewp_too_high"
            if outdoor_dewp > self.dewp_comfort_max
            else "outdoor_rh_too_high"
            if state.outdoor_humidity > self.rh_max
            else "outdoor_will_be_cool"
            if (
                indoor_ssi <= self.ssi_comfort_max
                and max(hourly_ssi) <= self.ssi_comfort_min
            )
            else None
        )

        hours_until_change = len(
            list(takewhile(lambda x: x == outdoor_comfort, hourly_comfort))
        )


class BinarySensorType(StrEnum):
    """Binary Sensor type enum."""

    OPEN_WINDOWS = "open_windows"


@dataclass
class MyBinarySensorEntityDescription(BinarySensorEntityDescription):
    """TODO."""

    sensor_class: type | None = None


BINARY_SENSOR_DESCRIPTIONS: list[MyBinarySensorEntityDescription] = [
    MyBinarySensorEntityDescription(
        sensor_class=OpenWindowsBinarySensor,
        key=BinarySensorType.OPEN_WINDOWS,
        device_class=BinarySensorDeviceClass.WINDOW,
        icon="mdi:window",
    ),
]

BINARY_SENSOR_TYPES = {desc.key: desc for desc in BINARY_SENSOR_DESCRIPTIONS}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up entity configured via user interface.

    Called via async_setup_platforms(, SENSOR) from __init__.py
    """
    config = config_entry.data | config_entry.options or {}
    device = hass.data[DOMAIN][config_entry.entry_id]

    _LOGGER.debug("async_setup_entry: %s", config_entry)

    entities: list[BinarySensorEntity] = [
        sensor_description.sensor_class(
            device=device,
            entity_description=sensor_description,
            sensor_type=sensor_type,
        )
        for sensor_type, sensor_description in BINARY_SENSOR_TYPES.items()
    ]

    if enabled_sensors := config.get(CONF_ENABLED_SENSORS):
        for entity in entities:
            if entity.entity_description.key not in enabled_sensors:
                entity.entity_description.entity_registry_enabled_default = False

    if entities:
        async_add_entities(entities)
