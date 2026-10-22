"""MeshMove: replace a device without breaking automations, dashboards and history."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import websocket
from .const import DOMAIN
from .swap import SwapManager


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MeshMove from a config entry."""
    manager = SwapManager(hass)
    await manager.async_load()
    hass.data[DOMAIN] = manager
    websocket.async_register(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hass.data.pop(DOMAIN, None)
    return True
