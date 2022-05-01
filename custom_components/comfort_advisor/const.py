"""General comfort_advisor constants."""
from datetime import timedelta
from enum import IntEnum
from typing import Final

from homeassistant.backports.enum import StrEnum
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntityDescription,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)

DOMAIN: Final = "comfort_advisor"

CONF_COMFORT: Final = "comfort"
CONF_DEVICE: Final = "device"
CONF_DEWPOINT_MAX: Final = "dew_point_max"
CONF_ENABLED_SENSORS: Final = "enabled_sensors"
CONF_HUMIDITY_MAX: Final = "humidity_max"
CONF_INDOOR_HUMIDITY: Final = "indoor_humidity"
CONF_INDOOR_TEMPERATURE: Final = "indoor_temperature"
CONF_INPUTS: Final = "inputs"
CONF_OUTDOOR_HUMIDITY: Final = "outdoor_humidity"
CONF_OUTDOOR_TEMPERATURE: Final = "outdoor_temperature"
CONF_POLL: Final = "poll"
CONF_POLLEN_MAX: Final = "pollen_max"
CONF_POLL_INTERVAL: Final = "poll_interval"
CONF_PROVIDER: Final = "provider"
CONF_PROVIDER_TYPE: Final = "provider_type"
CONF_SIMMER_INDEX_MAX: Final = "simmer_index_max"
CONF_SIMMER_INDEX_MIN: Final = "simmer_index_min"

# DataUpdateCoordinator constants
SCAN_INTERVAL_REALTIME: Final = timedelta(minutes=15)
SCAN_INTERVAL_FORECAST: Final = timedelta(hours=1)

# Default values
DEFAULT_NAME: Final = "Comfort Advisor"
DEFAULT_MANUFACTURER: Final = "@lymanepp"
DEFAULT_DEWPOINT_MAX: Final = 60
DEFAULT_HUMIDITY_MAX: Final = 95
DEFAULT_POLLEN_MAX: Final = 2
DEFAULT_SIMMER_INDEX_MAX: Final = 85
DEFAULT_SIMMER_INDEX_MIN: Final = 70
DEFAULT_POLL: Final = False
DEFAULT_POLL_INTERVAL: Final = 30


# can't be dynamic because providers are loaded on first use
PROVIDER_TYPES: Final[dict[str, str]] = {
    "fake": "Fake!",
    "nws": "National Weather Service",
    "tomorrowio": "Tomorrow.io",
}


class PollenIndex(IntEnum):
    """Pollen index."""

    NONE = 0
    VERY_LOW = 1
    LOW = 2
    MEDIUM = 3
    HIGH = 4
    VERY_HIGH = 5


class BinarySensorType(StrEnum):  # type: ignore
    """State class for comfort advisor binary sensors."""

    OPEN_WINDOWS = "open_windows"


BINARY_SENSOR_DESCRIPTIONS = [
    BinarySensorEntityDescription(
        key=BinarySensorType.OPEN_WINDOWS,
        device_class=BinarySensorDeviceClass.WINDOW,
        icon="mdi:window",
    ),
]

# TODO: can this be done with StrEnum and move BINARY_SENSOR_DESCRIPTIONS back to its place?
ALL_BINARY_SENSOR_TYPES: list[str] = sorted(x.key for x in BINARY_SENSOR_DESCRIPTIONS)


class SensorType(StrEnum):  # type: ignore
    """State class for comfort advisor sensors."""

    OPEN_WINDOWS_REASON = "open_windows_reason"
    NEXT_CHANGE_TIME = "next_change_time"
    HIGH_SIMMER_INDEX = "high_simmer_index"


class DeviceClass(StrEnum):  # type: ignore
    """State class for comfort advisor sensors."""

    OPEN_WINDOWS_REASON = f"{DOMAIN}__{SensorType.OPEN_WINDOWS_REASON}"


SENSOR_DESCRIPTIONS = [
    SensorEntityDescription(
        key=SensorType.OPEN_WINDOWS_REASON,
        device_class=DeviceClass.OPEN_WINDOWS_REASON,
        # icon="mdi:water",
    ),
    SensorEntityDescription(
        key=SensorType.NEXT_CHANGE_TIME,
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key=SensorType.HIGH_SIMMER_INDEX,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
]


# TODO: can this be done with StrEnum and move SENSOR_DESCRIPTIONS back to its place?
ALL_SENSOR_TYPES: list[str] = sorted(x.key for x in SENSOR_DESCRIPTIONS)
