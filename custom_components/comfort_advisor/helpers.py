"""Helper functions."""
from __future__ import annotations

import asyncio
import importlib
import logging
import sys
from types import ModuleType
from typing import Any, Callable, Coroutine, Iterable, Sequence, TypeVar, cast

from aiohttp.web_exceptions import HTTPServerError
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import ATTR_DEVICE_CLASS, ATTR_UNIT_OF_MEASUREMENT, Platform
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import device_registry, entity_registry
from homeassistant.loader import Integration, async_get_custom_components
from homeassistant.requirements import RequirementsNotFound, async_process_requirements
from yarl import URL

from .const import DOMAIN

if sys.version_info >= (3, 10):
    from typing import ParamSpec
else:
    from typing_extensions import ParamSpec

_LOGGER = logging.getLogger(__name__)

_ParamT = ParamSpec("_ParamT")
_ResultT = TypeVar("_ResultT")

EXCLUDED_PLATFORMS = (DOMAIN, "thermal_comfort")


def get_sensor_entities(
    hass: HomeAssistant,
    device_class: SensorDeviceClass,
    valid_units: Iterable[str],
) -> Sequence[str]:
    """Get list of sensor entities matching device_class and valid_units."""

    def include_sensors(state: State) -> bool:
        if not (
            state.domain == Platform.SENSOR
            and state.attributes.get(ATTR_DEVICE_CLASS) == device_class
            and state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) in valid_units
        ):
            return False

        return not (entity := ent_reg.async_get(state.entity_id)) or (
            not entity.hidden and entity.platform not in EXCLUDED_PLATFORMS
        )

    ent_reg = entity_registry.async_get(hass)
    all_states = hass.states.async_all()
    return [state.entity_id for state in filter(include_sensors, all_states)]


async def load_module(hass: HomeAssistant, name: str) -> ModuleType:
    """Load a Python module."""

    try:
        module = importlib.import_module(f"{__package__}.{name}")
    except ImportError as exc:
        _LOGGER.error("Unable to load module %s: %s", name, exc)
        raise

    if hass.config.skip_pip or not hasattr(module, "REQUIREMENTS"):
        return module

    processed = hass.data.setdefault(DOMAIN, {}).setdefault("reqs_processed", set())
    if name in processed:
        return module

    reqs = module.REQUIREMENTS
    try:
        await async_process_requirements(hass, f"module {name}", reqs)
    except RequirementsNotFound as exc:
        _LOGGER.error("Unable to satisfy requirements %s: %s", name, exc)
        raise

    processed.add(name)
    return module


async def create_issue_tracker_url(hass: HomeAssistant, exc: Exception, *, title: str) -> str:
    """Create an issue tracker URL."""
    custom_components = await async_get_custom_components(hass)
    integration: Integration = custom_components[DOMAIN]
    url = URL(integration.issue_tracker) / "new"
    body = f"**Integration:** {integration.name}\n**Version:** {integration.version}"
    if msg := getattr(exc, "msg"):
        body += f"\n**Message:** {msg}"
    url = url.with_query({"title": title, "body": body})
    return str(url)


def async_retry(
    wrapped: Callable[_ParamT, Coroutine[Any, Any, _ResultT]]
) -> Callable[_ParamT, Coroutine[Any, Any, _ResultT]]:
    """`HTTPServerError` retry handler."""

    async def wrapper(*args: _ParamT.args, **kwargs: _ParamT.kwargs) -> _ResultT:
        retries = 5
        while True:
            try:
                return await wrapped(*args, **kwargs)
            except HTTPServerError:
                retries -= 1
                if retries == 0:
                    raise
            except Exception as exc:
                _LOGGER.exception("%s from pynws", type(exc), exc_info=exc)
                raise
            await asyncio.sleep(1)

    return wrapper


def get_entity_area(hass: HomeAssistant, entity_id: str) -> str | None:
    """Get the area of an entity (if one is assigned)."""
    ent_reg = entity_registry.async_get(hass)
    entity = ent_reg.async_get(entity_id)
    if entity.area_id:
        return cast(str, entity.area_id)

    dev_reg = device_registry.async_get(hass)
    device = dev_reg.async_get(entity.device_id)
    return cast(str, device.area_id)
