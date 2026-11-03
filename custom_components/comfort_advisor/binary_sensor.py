"""Binary sensor platform for comfort_advisor."""

from collections.abc import Mapping
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .comfort import Calculated
from .const import CONF_ENABLED_SENSORS
from .device import ComfortAdvisorConfigEntry, ComfortAdvisorDevice


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ComfortAdvisorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the "can open windows" binary sensor."""
    config = config_entry.data | config_entry.options
    enabled = Calculated.CAN_OPEN_WINDOWS in config[CONF_ENABLED_SENSORS]
    async_add_entities([CanOpenWindowsBinarySensor(config_entry.runtime_data, enabled)])


class CanOpenWindowsBinarySensor(BinarySensorEntity):
    """Whether windows can be open, shown as Yes/No, with the reason as an attribute."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = Calculated.CAN_OPEN_WINDOWS

    def __init__(self, device: ComfortAdvisorDevice, enabled_default: bool) -> None:
        """Initialize the binary sensor."""
        self._device = device
        self._attr_device_info = device.device_info
        self._attr_entity_registry_enabled_default = enabled_default
        self._attr_unique_id = f"{device.unique_id}_{Calculated.CAN_OPEN_WINDOWS}"

    async def async_added_to_hass(self) -> None:
        """Write the state whenever the calculated values change."""
        self.async_on_remove(self._device.async_add_listener(self.async_write_ha_state))

    @property
    def available(self) -> bool:
        """Unavailable while any input is unavailable."""
        return self._device.available

    @property
    def is_on(self) -> bool | None:
        """Return True if windows can be open."""
        value: bool | None = self._device.get_calculated(Calculated.CAN_OPEN_WINDOWS)
        return value

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return the reason for the advice."""
        return dict(self._device.extra_attributes)
