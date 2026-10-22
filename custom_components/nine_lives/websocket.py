"""WebSocket commands used by the Nine Lives panel. All of them need an admin."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .matching import EntityInfo, propose_pairs
from .swap import SwapError, SwapManager, async_plan

_DEVICES = {
    vol.Required("old_device_id"): str,
    vol.Required("new_device_id"): str,
}
_PAIRS = {
    vol.Required("pairs"): [
        vol.Schema({vol.Required("old"): str, vol.Required("new"): str})
    ],
}


@callback
def async_register(hass: HomeAssistant) -> None:
    for command in (ws_propose, ws_preview, ws_apply, ws_backups, ws_undo):
        websocket_api.async_register_command(hass, command)


def _manager(hass: HomeAssistant) -> SwapManager:
    return hass.data[DOMAIN]


def _entity_infos(hass: HomeAssistant, device_id: str) -> list[EntityInfo]:
    infos = []
    for entry in er.async_entries_for_device(er.async_get(hass), device_id):
        state = hass.states.get(entry.entity_id)
        attrs = state.attributes if state else {}
        infos.append(
            EntityInfo(
                entity_id=entry.entity_id,
                registry_id=entry.id,
                device_class=entry.device_class or entry.original_device_class,
                unit=entry.unit_of_measurement or attrs.get("unit_of_measurement"),
                state_class=(entry.capabilities or {}).get("state_class"),
                name=entry.name or entry.original_name,
            )
        )
    return infos


def _pairs(msg: dict[str, Any]) -> list[tuple[str, str]]:
    return [(p["old"], p["new"]) for p in msg["pairs"]]


@websocket_api.websocket_command(
    {vol.Required("type"): "nine_lives/propose", **_DEVICES}
)
@websocket_api.require_admin
@callback
def ws_propose(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Suggest which entities of the new device replace which of the old one."""
    result = propose_pairs(
        _entity_infos(hass, msg["old_device_id"]),
        _entity_infos(hass, msg["new_device_id"]),
    )
    connection.send_result(
        msg["id"],
        {
            "pairs": [
                {"old": o.entity_id, "new": n.entity_id} for o, n in result.pairs
            ],
            "unmatched_old": [e.entity_id for e in result.unmatched_old],
            "unmatched_new": [e.entity_id for e in result.unmatched_new],
        },
    )


@websocket_api.websocket_command(
    {vol.Required("type"): "nine_lives/preview", **_DEVICES, **_PAIRS}
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_preview(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Show everything a swap would change, without changing anything."""
    try:
        plan = await async_plan(
            hass, msg["old_device_id"], msg["new_device_id"], _pairs(msg)
        )
    except SwapError as err:
        connection.send_error(msg["id"], "invalid", str(err))
        return
    connection.send_result(msg["id"], plan.as_dict())


@websocket_api.websocket_command(
    {vol.Required("type"): "nine_lives/apply", **_DEVICES, **_PAIRS}
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_apply(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Swap the devices; the plan is worked out again to match the current state."""
    try:
        plan = await async_plan(
            hass, msg["old_device_id"], msg["new_device_id"], _pairs(msg)
        )
        backup_id = await _manager(hass).async_apply(plan)
    except SwapError as err:
        connection.send_error(msg["id"], "invalid", str(err))
        return
    connection.send_result(msg["id"], {"backup_id": backup_id})


@websocket_api.websocket_command({vol.Required("type"): "nine_lives/backups"})
@websocket_api.require_admin
@callback
def ws_backups(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """List the swaps that can still be undone, newest first."""
    backups = sorted(
        _manager(hass).backups.items(), key=lambda b: b[1]["created"], reverse=True
    )
    connection.send_result(
        msg["id"],
        [
            {
                "backup_id": backup_id,
                "created": b["created"],
                "old_device": b["old_device"]["name"],
                "new_device": b["new_device"]["name"],
                "entities": [p["old"]["entity_id"] for p in b["pairs"]],
            }
            for backup_id, b in backups
        ],
    )


@websocket_api.websocket_command(
    {vol.Required("type"): "nine_lives/undo", vol.Required("backup_id"): str}
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_undo(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Undo a swap."""
    try:
        notes = await _manager(hass).async_undo(msg["backup_id"])
    except SwapError as err:
        connection.send_error(msg["id"], "invalid", str(err))
        return
    connection.send_result(msg["id"], {"notes": notes})
