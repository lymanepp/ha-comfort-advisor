"""TODO."""
from __future__ import annotations

import importlib
import logging
from types import ModuleType

from homeassistant.core import HomeAssistant
from homeassistant.loader import Integration, async_get_custom_components
from homeassistant.requirements import RequirementsNotFound, async_process_requirements
from yarl import URL

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
