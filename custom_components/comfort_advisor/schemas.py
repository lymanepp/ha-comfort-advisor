"""Config flow schemas for comfort_advisor."""

from collections.abc import Mapping, Sequence
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.weather import ATTR_FORECAST_HUMIDITY
from homeassistant.components.weather.const import DOMAIN as WEATHER_DOMAIN
from homeassistant.components.weather.const import SERVICE_GET_FORECASTS, WeatherEntityFeature
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_NAME,
    CONF_TEMPERATURE_UNIT,
    PERCENTAGE,
    Platform,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entityfilter import CONF_INCLUDE_ENTITIES
from homeassistant.helpers.selector import selector
from homeassistant.util.unit_conversion import TemperatureConverter as TC
from homeassistant.util.unit_system import METRIC_SYSTEM
import probatio

from .comfort import Calculated
from .const import (
    _LOGGER,
    CONF_COOLING_TEMPERATURE_MIN,
    CONF_DEW_POINT_MAX,
    CONF_ENABLED_SENSORS,
    CONF_HUMIDITY_HYSTERESIS,
    CONF_HUMIDITY_MAX,
    CONF_HYSTERESIS,
    CONF_INDOOR_HUMIDITY,
    CONF_INDOOR_TEMPERATURE,
    CONF_OUTDOOR_HUMIDITY,
    CONF_OUTDOOR_TEMPERATURE,
    CONF_POLLEN_MAX,
    CONF_SIMMER_INDEX_MAX,
    CONF_SIMMER_INDEX_MIN,
    CONF_TEMPERATURE_TOLERANCE,
    CONF_WEATHER,
    DEFAULT_COOLING_TEMPERATURE_MIN,
    DEFAULT_DEWPOINT_MAX,
    DEFAULT_HUMIDITY_HYSTERESIS,
    DEFAULT_HUMIDITY_MAX,
    DEFAULT_HYSTERESIS,
    DEFAULT_NAME,
    DEFAULT_POLLEN_MAX,
    DEFAULT_SIMMER_INDEX_MAX,
    DEFAULT_SIMMER_INDEX_MIN,
    DEFAULT_TEMPERATURE_TOLERANCE,
)
from .helpers import domain_entity_ids

ALL_SENSOR_TYPES = [str(x) for x in Calculated]

VALID_TEMP_UNITS = [
    UnitOfTemperature.CELSIUS,
    UnitOfTemperature.FAHRENHEIT,
]


async def _forecast_has_humidity(hass: HomeAssistant, entity_id: str) -> bool:
    """Return True if the entity's hourly forecast includes humidity."""
    try:
        response = await hass.services.async_call(
            WEATHER_DOMAIN,
            SERVICE_GET_FORECASTS,
            service_data={"type": "hourly"},
            target={ATTR_ENTITY_ID: entity_id},
            blocking=True,
            return_response=True,
        )
    except Exception:
        _LOGGER.debug("Could not get the hourly forecast of %s", entity_id, exc_info=True)
        return False

    return (
        isinstance(response, Mapping)
        and isinstance(entity_forecast := response.get(entity_id), Mapping)
        and isinstance(forecast := entity_forecast.get("forecast"), Sequence)
        and len(forecast) > 0
        and isinstance(forecast[0], Mapping)
        and forecast[0].get(ATTR_FORECAST_HUMIDITY) is not None
    )


async def build_inputs_schema(hass: HomeAssistant, config: Mapping[str, Any]) -> probatio.Schema:
    """Build inputs schema."""
    weather = config.get(CONF_WEATHER, probatio.UNDEFINED)
    indoor_temperature = config.get(CONF_INDOOR_TEMPERATURE, probatio.UNDEFINED)
    indoor_humidity = config.get(CONF_INDOOR_HUMIDITY, probatio.UNDEFINED)
    outdoor_temperature = config.get(CONF_OUTDOOR_TEMPERATURE, probatio.UNDEFINED)
    outdoor_humidity = config.get(CONF_OUTDOOR_HUMIDITY, probatio.UNDEFINED)

    weather_entity_ids = domain_entity_ids(
        hass, Platform.WEATHER, required_features=WeatherEntityFeature.FORECAST_HOURLY
    )
    temp_sensors = domain_entity_ids(
        hass, Platform.SENSOR, SensorDeviceClass.TEMPERATURE, VALID_TEMP_UNITS
    )
    humidity_sensors = domain_entity_ids(
        hass, Platform.SENSOR, SensorDeviceClass.HUMIDITY, PERCENTAGE
    )

    weather_entity_ids = [id for id in weather_entity_ids if await _forecast_has_humidity(hass, id)]

    weather_selector = selector({"entity": {CONF_INCLUDE_ENTITIES: weather_entity_ids}})
    temp_sensor_selector = selector({"entity": {CONF_INCLUDE_ENTITIES: temp_sensors}})
    humidity_sensor_selector = selector({"entity": {CONF_INCLUDE_ENTITIES: humidity_sensors}})

    return probatio.Schema(
        {
            probatio.Required(CONF_WEATHER, default=weather): weather_selector,
            probatio.Required(
                CONF_INDOOR_TEMPERATURE, default=indoor_temperature
            ): temp_sensor_selector,
            probatio.Required(
                CONF_INDOOR_HUMIDITY, default=indoor_humidity
            ): humidity_sensor_selector,
            probatio.Required(
                CONF_OUTDOOR_TEMPERATURE, default=outdoor_temperature
            ): temp_sensor_selector,
            probatio.Required(
                CONF_OUTDOOR_HUMIDITY, default=outdoor_humidity
            ): humidity_sensor_selector,
        }
    )


def build_comfort_schema(hass: HomeAssistant, config: Mapping[str, Any]) -> probatio.Schema:
    """Build comfort settings schema."""
    temp_unit = hass.config.units.temperature_unit

    simmer_index_min = config.get(
        CONF_SIMMER_INDEX_MIN,
        round(TC.convert(DEFAULT_SIMMER_INDEX_MIN, UnitOfTemperature.FAHRENHEIT, temp_unit), 1),
    )
    simmer_index_max = config.get(
        CONF_SIMMER_INDEX_MAX,
        round(TC.convert(DEFAULT_SIMMER_INDEX_MAX, UnitOfTemperature.FAHRENHEIT, temp_unit), 1),
    )
    dew_point_max = config.get(
        CONF_DEW_POINT_MAX,
        round(TC.convert(DEFAULT_DEWPOINT_MAX, UnitOfTemperature.FAHRENHEIT, temp_unit), 1),
    )
    humidity_max = config.get(CONF_HUMIDITY_MAX, DEFAULT_HUMIDITY_MAX)
    pollen_max: int = config.get(CONF_POLLEN_MAX, DEFAULT_POLLEN_MAX)
    cooling_temperature_min = config.get(
        CONF_COOLING_TEMPERATURE_MIN,
        round(
            TC.convert(DEFAULT_COOLING_TEMPERATURE_MIN, UnitOfTemperature.FAHRENHEIT, temp_unit),
            1,
        ),
    )
    hysteresis = config.get(
        CONF_HYSTERESIS,
        round(TC.convert_interval(DEFAULT_HYSTERESIS, UnitOfTemperature.FAHRENHEIT, temp_unit), 1),
    )
    humidity_hysteresis = config.get(CONF_HUMIDITY_HYSTERESIS, DEFAULT_HUMIDITY_HYSTERESIS)
    temperature_tolerance = config.get(
        CONF_TEMPERATURE_TOLERANCE,
        round(
            TC.convert_interval(
                DEFAULT_TEMPERATURE_TOLERANCE, UnitOfTemperature.FAHRENHEIT, temp_unit
            ),
            1,
        ),
    )

    temp_step = 0.5 if hass.config.units is METRIC_SYSTEM else 1.0
    temperature_selector = selector(
        {"number": {"mode": "box", "unit_of_measurement": temp_unit, "step": temp_step}}
    )
    tolerance_selector = selector(
        {
            "number": {
                "mode": "box",
                "unit_of_measurement": temp_unit,
                "step": temp_step / 2,
                "min": 0,
                "max": 5,
            }
        }
    )
    humidity_margin_selector = selector(
        {
            "number": {
                "mode": "box",
                "unit_of_measurement": PERCENTAGE,
                "step": 0.5,
                "min": 0,
                "max": 10,
            }
        }
    )
    humidity_selector = selector(
        {"number": {"mode": "slider", "unit_of_measurement": PERCENTAGE, "min": 50, "max": 100}}
    )

    return probatio.Schema(
        {
            probatio.Required(
                CONF_SIMMER_INDEX_MIN, default=simmer_index_min
            ): temperature_selector,
            probatio.Required(
                CONF_SIMMER_INDEX_MAX, default=simmer_index_max
            ): temperature_selector,
            probatio.Required(CONF_DEW_POINT_MAX, default=dew_point_max): temperature_selector,
            probatio.Required(CONF_HUMIDITY_MAX, default=humidity_max): probatio.All(
                humidity_selector
            ),
            probatio.Required(CONF_POLLEN_MAX, default=pollen_max): probatio.In(
                {0: "none", 1: "very_low", 2: "low", 3: "medium", 4: "high", 5: "very_high"}  # TODO
            ),
            probatio.Required(
                CONF_COOLING_TEMPERATURE_MIN, default=cooling_temperature_min
            ): temperature_selector,
            probatio.Required(
                CONF_TEMPERATURE_TOLERANCE, default=temperature_tolerance
            ): tolerance_selector,
            probatio.Required(CONF_HYSTERESIS, default=hysteresis): tolerance_selector,
            probatio.Required(
                CONF_HUMIDITY_HYSTERESIS, default=humidity_hysteresis
            ): humidity_margin_selector,
        }
    )


def build_device_schema(config: Mapping[str, Any]) -> probatio.Schema:
    """Build device settings schema."""
    name: str = config.get(CONF_NAME, DEFAULT_NAME)
    enabled_sensors: Sequence[str] = config.get(CONF_ENABLED_SENSORS, ALL_SENSOR_TYPES)

    all_sensor_types = sorted(ALL_SENSOR_TYPES)
    sensor_type_dict = {x: x.replace("_", " ").title() for x in all_sensor_types}
    return probatio.Schema(
        {
            probatio.Required(CONF_NAME, default=name): str,
            probatio.Required(
                CONF_ENABLED_SENSORS, default=enabled_sensors or all_sensor_types
            ): cv.multi_select(sensor_type_dict),
        }
    )


DATA_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_WEATHER): cv.entity_id,
        probatio.Required(CONF_INDOOR_TEMPERATURE): cv.entity_id,
        probatio.Required(CONF_INDOOR_HUMIDITY): cv.entity_id,
        probatio.Required(CONF_OUTDOOR_TEMPERATURE): cv.entity_id,
        probatio.Required(CONF_OUTDOOR_HUMIDITY): cv.entity_id,
        probatio.Required(CONF_SIMMER_INDEX_MIN): probatio.Coerce(float),
        probatio.Required(CONF_SIMMER_INDEX_MAX): probatio.Coerce(float),
        probatio.Required(CONF_DEW_POINT_MAX): probatio.Coerce(float),
        probatio.Required(CONF_HUMIDITY_MAX): probatio.Coerce(float),
        probatio.Required(CONF_POLLEN_MAX): probatio.All(
            probatio.Coerce(int), probatio.Range(min=0, max=5)
        ),
        probatio.Required(CONF_COOLING_TEMPERATURE_MIN): probatio.Coerce(float),
        probatio.Required(CONF_TEMPERATURE_TOLERANCE): probatio.All(
            probatio.Coerce(float), probatio.Range(min=0)
        ),
        probatio.Required(CONF_HYSTERESIS): probatio.All(
            probatio.Coerce(float), probatio.Range(min=0)
        ),
        probatio.Required(CONF_HUMIDITY_HYSTERESIS): probatio.All(
            probatio.Coerce(float), probatio.Range(min=0)
        ),
        probatio.Required(CONF_TEMPERATURE_UNIT): probatio.In(VALID_TEMP_UNITS),
        probatio.Required(CONF_NAME): probatio.All(str, probatio.Length(min=1)),
        probatio.Required(CONF_ENABLED_SENSORS): cv.multi_select(ALL_SENSOR_TYPES),
    }
)
