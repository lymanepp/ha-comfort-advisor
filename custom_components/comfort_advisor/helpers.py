"""TODO."""

import importlib
import logging
from types import ModuleType

from homeassistant.core import HomeAssistant
from homeassistant.requirements import async_process_requirements

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


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
    await async_process_requirements(hass, f"module {name}", reqs)

    processed.add(name)
    return module
