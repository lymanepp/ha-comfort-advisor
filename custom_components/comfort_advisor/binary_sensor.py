"""Sensor platform for comfort_advisor."""
from __future__ import annotations

from copy import copy
from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.backports.enum import StrEnum
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
    ENTITY_ID_FORMAT,
    PLATFORM_SCHEMA,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ENTITY_PICTURE_TEMPLATE,
    CONF_FRIENDLY_NAME,
    CONF_ICON_TEMPLATE,
    CONF_NAME,
    CONF_SENSORS,
    CONF_UNIQUE_ID,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import TemplateError
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import (
    DeviceInfo,
    async_generate_entity_id,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.template import Template
import voluptuous as vol

from .device import ComfortAdvisorDevice
from .const import (
    CONF_ENABLED_SENSORS,
    CONF_INDOOR_HUMIDITY_SENSOR,
    CONF_INDOOR_TEMPERATURE_SENSOR,
    CONF_POLL,
    CONF_POLL_INTERVAL,
    CONF_SENSOR_TYPES,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class ComfortAdvisorBinarySensor(BinarySensorEntity):
    """Representation of a Comfort Advisor binary sensor."""

    def __init__(
        self,
        *,
        device: ComfortAdvisorDevice,
        sensor_type: BinarySensorType,
        entity_description: BinarySensorEntityDescription,
        icon_template: Template = None,
        entity_picture_template: Template = None,
        friendly_name: str = None,
    ) -> None:
        """Initialize the sensor."""
        self._device = device
        self._sensor_type = sensor_type
        self.entity_description = copy(entity_description)

        if friendly_name is None:
            self.entity_description.name = f"{self._device.name} {self._sensor_type}"
        else:
            self.entity_description.name = f"{friendly_name} {self._sensor_type}"

        self.entity_id = async_generate_entity_id(
            ENTITY_ID_FORMAT,
            f"{self._device.name}_{self._sensor_type}",
            hass=self._device.hass,
        )

        self._icon_template = icon_template
        self._entity_picture_template = entity_picture_template

        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
        if self._device.unique_id:
            self._attr_unique_id = id_generator(self._device.unique_id, sensor_type)
        self._attr_should_poll = False

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return self._device.device_info

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return dict(
            self._device.extra_state_attributes, **self._attr_extra_state_attributes
        )

    async def async_added_to_hass(self):
        """Register callbacks."""
        self._device.sensors.append(self)

        if self._icon_template is not None:
            self._icon_template.hass = self.hass

        if self._entity_picture_template is not None:
            self._entity_picture_template.hass = self.hass

        # TODO
        # if self._device.get_compute_state(self._sensor_type).needs_update:
        #    self.async_schedule_update_ha_state(True)

    def update_template_values(self) -> None:
        """TODO."""
        for property_name, template in (
            ("_attr_icon", self._icon_template),
            ("_attr_entity_picture", self._entity_picture_template),
        ):
            if template is None:
                continue

            try:
                setattr(self, property_name, template.async_render())
            except TemplateError as ex:
                friendly_property_name = property_name[1:].replace("_", " ")
                if ex.args and ex.args[0].startswith(
                    "UndefinedError: 'None' has no attribute"
                ):
                    # Common during HA startup - so just a warning
                    _LOGGER.warning(
                        "Could not render %s template %s," " the state is unknown.",
                        friendly_property_name,
                        self.name,
                    )
                    continue

                try:
                    setattr(self, property_name, getattr(super(), property_name))
                except AttributeError:
                    _LOGGER.error(
                        "Could not render %s template %s: %s",
                        friendly_property_name,
                        self.name,
                        ex,
                    )

    async def async_update(self):
        """Update the state of the sensor."""
        # self._attr_native_value = False
        # self.update_template_values()


class BinarySensorType(StrEnum):
    """Binary Sensor type enum."""

    OPEN_WINDOWS = "open_windows"


@dataclass
class MyBinarySensorEntityDescription(BinarySensorEntityDescription):
    """TODO."""

    sensor_class: type | None = None


BINARY_SENSOR_DESCRIPTIONS: list[MyBinarySensorEntityDescription] = [
    MyBinarySensorEntityDescription(
        sensor_class=ComfortAdvisorBinarySensor,
        key=BinarySensorType.OPEN_WINDOWS,
        device_class=BinarySensorDeviceClass.WINDOW,
        icon="mdi:window",
    ),
]

BINARY_SENSOR_TYPES = {desc.key: desc for desc in BINARY_SENSOR_DESCRIPTIONS}

PLATFORM_OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_POLL): cv.boolean,
        vol.Optional(CONF_POLL_INTERVAL): cv.time_period,
        vol.Optional(CONF_SENSOR_TYPES): cv.ensure_list,
    },
    extra=vol.REMOVE_EXTRA,
)

LEGACY_SENSOR_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_INDOOR_TEMPERATURE_SENSOR): cv.entity_id,
        vol.Required(CONF_INDOOR_HUMIDITY_SENSOR): cv.entity_id,
        vol.Optional(CONF_ICON_TEMPLATE): cv.template,
        vol.Optional(CONF_ENTITY_PICTURE_TEMPLATE): cv.template,
        vol.Optional(CONF_FRIENDLY_NAME): cv.string,
        vol.Optional(CONF_UNIQUE_ID): cv.string,
    }
)

SENSOR_SCHEMA = LEGACY_SENSOR_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME): cv.string,
    }
).extend(PLATFORM_OPTIONS_SCHEMA.schema)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_SENSORS): cv.schema_with_slug_keys(SENSOR_SCHEMA),
    }
).extend(PLATFORM_OPTIONS_SCHEMA.schema)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up entity configured via user interface.

    Called via async_setup_platforms(, SENSOR) from __init__.py
    """
    config = entry.data | entry.options or {}
    device = hass.data[DOMAIN][entry.entry_id]

    _LOGGER.debug("async_setup_entry: %s", entry)

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


def id_generator(unique_id: str, sensor_type: str) -> str:
    """Generate id based on unique_id and sensor type.

    :param unique_id: str: common part of id for all entities, device unique_id, as a rule
    :param sensor_type: str: different part of id, sensor type, as s rule
    :returns: str: unique_id+sensor_type
    """
    return unique_id + sensor_type
