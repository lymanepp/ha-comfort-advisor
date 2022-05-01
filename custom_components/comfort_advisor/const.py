"""General comfort_advisor constants."""
from datetime import timedelta
from enum import IntEnum
from typing import Final

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntityDescription,
)
from homeassistant.components.sensor import (
    SensorEntityDescription,
    SensorDeviceClass,
    SensorStateClass,
)

from homeassistant.backports.enum import StrEnum

DOMAIN: Final = "comfort_advisor"

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


class SectionConfig(StrEnum):  # type: ignore
    """Configuration schema enum."""

    PROVIDER = "provider"
    INPUTS = "inputs"
    COMFORT = "comfort"
    DEVICE = "device"


class ProviderConfig(StrEnum):  # type: ignore
    """Configuration provider enum."""

    TYPE = "type"


class InputConfig(StrEnum):  # type: ignore
    """Configuration section enum."""

    INDOOR_HUMIDITY = "indoor_humidity"
    INDOOR_TEMPERATURE = "indoor_temp"
    OUTDOOR_HUMIDITY = "outdoor_humidity"
    OUTDOOR_TEMPERATURE = "outdoor_temp"
    OUTDOOR_POLLEN = "outdoor_pollen"


class ComfortConfig(StrEnum):  # type: ignore
    """Configuration comfort enum."""

    DEWPOINT_MAX = "dew_point_max"
    HUMIDITY_MAX = "humidity_max"
    POLLEN_MAX = "pollen_max"
    SIMMER_INDEX_MAX = "simmer_index_max"
    SIMMER_INDEX_MIN = "simmer_index_min"


class DeviceConfig(StrEnum):  # type: ignore
    """Configuration value enum."""

    ENABLED_SENSORS = "enabled_sensors"
    NAME = "name"
    POLL = "poll"
    POLL_INTERVAL = "poll_interval"


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

BINARY_SENSOR_TYPES: list[str] = sorted([x.key for x in BINARY_SENSOR_DESCRIPTIONS])


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


SENSOR_TYPES: list[str] = sorted([x.key for x in SENSOR_DESCRIPTIONS])
