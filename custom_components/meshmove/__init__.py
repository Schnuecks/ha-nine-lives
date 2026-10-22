"""MeshMove: replace a device without breaking automations, dashboards and history."""

from __future__ import annotations

import hashlib
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import websocket
from .const import DOMAIN
from .swap import SwapManager

PANEL_URL = "meshmove"
STATIC_URL = "/meshmove_static"
PANEL_JS = Path(__file__).parent / "frontend" / "meshmove-panel.js"
_STATIC_REGISTERED = f"{DOMAIN}_static_registered"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MeshMove from a config entry."""
    manager = SwapManager(hass)
    await manager.async_load()
    hass.data[DOMAIN] = manager
    websocket.async_register(hass)

    # Static paths cannot be removed again, so they are registered once per run.
    if not hass.data.get(_STATIC_REGISTERED):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, str(PANEL_JS.parent), cache_headers=False)]
        )
        hass.data[_STATIC_REGISTERED] = True
    # The hash makes browsers load a changed panel after an update.
    digest = await hass.async_add_executor_job(
        lambda: hashlib.sha256(PANEL_JS.read_bytes()).hexdigest()[:12]
    )
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL,
        webcomponent_name="meshmove-panel",
        module_url=f"{STATIC_URL}/{PANEL_JS.name}?v={digest}",
        sidebar_title="MeshMove",
        sidebar_icon="mdi:swap-horizontal-bold",
        require_admin=True,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    frontend.async_remove_panel(hass, PANEL_URL, warn_if_unknown=False)
    hass.data.pop(DOMAIN, None)
    return True
