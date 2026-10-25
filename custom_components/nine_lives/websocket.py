"""WebSocket commands used by the Nine Lives panel. All of them need an admin."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.loader import IntegrationNotLoaded, async_get_loaded_integration

from . import deleted, energy
from .const import DOMAIN
from .matching import EntityInfo, propose_pairs
from .swap import SwapError, SwapManager, async_plan, async_suggest_ids

_DEVICES = {
    vol.Required("old_device_id"): str,
    vol.Required("new_device_id"): str,
}
_PAIRS = {
    vol.Required("pairs"): [
        vol.Schema(
            {
                vol.Required("old"): str,
                vol.Required("new"): str,
                vol.Optional("new_entity_id"): vol.Any(str, None),
            }
        )
    ],
}


@callback
def async_register(hass: HomeAssistant) -> None:
    for command in (
        ws_devices,
        ws_removed_devices,
        ws_propose,
        ws_preview,
        ws_apply,
        ws_backups,
        ws_undo,
        ws_pending,
    ):
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


def _new_ids(msg: dict[str, Any]) -> dict[str, str]:
    return {
        p["old"]: p["new_entity_id"] for p in msg["pairs"] if p.get("new_entity_id")
    }


@websocket_api.websocket_command(
    {vol.Required("type"): "nine_lives/propose", **_DEVICES}
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_propose(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Suggest which entities of the new device replace which of the old one.

    Old IDs that no longer match their name and are not used anywhere come with a
    suggested tidier ID.
    """
    removed = deleted.removed_device(hass, msg["old_device_id"])
    removed_details: dict[str, dict[str, Any]] = {}
    if removed is not None:
        last = await deleted.async_last_states(
            hass, [e.entity_id for e in removed.entities]
        )
        old_infos = deleted.entity_infos(removed, last)
        # The panel cannot see removed entities; it shows their last name and value.
        for info in old_infos:
            state = last.get(info.entity_id)
            unit = state.attributes.get("unit_of_measurement") if state else None
            removed_details[info.entity_id] = {
                "name": info.name,
                "value": f"{state.state} {unit}"
                if state and unit
                else (state.state if state else None),
            }
    else:
        old_infos = _entity_infos(hass, msg["old_device_id"])
    result = propose_pairs(old_infos, _entity_infos(hass, msg["new_device_id"]))
    olds = [o.entity_id for o, _ in result.pairs] + [
        e.entity_id for e in result.unmatched_old
    ]
    suggestions = await async_suggest_ids(hass, olds)
    usage = {old: s["used_in"] for old, s in suggestions.items()}
    connection.send_result(
        msg["id"],
        {
            "pairs": [
                {"old": o.entity_id, "new": n.entity_id} for o, n in result.pairs
            ],
            "suggested_ids": {old: s["id"] for old, s in suggestions.items()},
            "suggested_usage": usage,
            "removed_details": removed_details,
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
            hass, msg["old_device_id"], msg["new_device_id"], _pairs(msg), _new_ids(msg)
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
            hass, msg["old_device_id"], msg["new_device_id"], _pairs(msg), _new_ids(msg)
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
    """All swaps with what they did, newest first; can_undo marks the undoable ones."""
    manager = _manager(hass)
    swaps = sorted(manager.history.items(), key=lambda s: s[1]["created"], reverse=True)
    connection.send_result(
        msg["id"],
        [
            {
                **entry,
                "backup_id": swap_id,
                "entities": [p["final"] for p in entry["pairs"]],
                "can_undo": manager.can_undo(swap_id),
                "old_device_removed": manager.old_device_removed(swap_id),
            }
            for swap_id, entry in swaps
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


@websocket_api.websocket_command({vol.Required("type"): "nine_lives/pending"})
@websocket_api.require_admin
@callback
def ws_pending(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Meter sum corrections still waiting for the recorder, with when they are due."""
    connection.send_result(
        msg["id"],
        [
            {**item, "due": energy.next_check(item).isoformat()}
            for item in _manager(hass).pending
        ],
    )


def _integration_name(hass: HomeAssistant, entry_id: str | None) -> str | None:
    entry = hass.config_entries.async_get_entry(entry_id) if entry_id else None
    if entry is None:
        return None
    try:
        return async_get_loaded_integration(hass, entry.domain).name
    except IntegrationNotLoaded:
        return entry.domain


@websocket_api.websocket_command({vol.Required("type"): "nine_lives/devices"})
@websocket_api.require_admin
@callback
def ws_devices(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Devices that can take part in a swap, with what helps to tell them apart.

    created_at tells old from new, available shows an unplugged or broken device and
    identify names a button that makes the device blink or beep, if it has one.
    """
    ent_reg = er.async_get(hass)
    devices = []
    for device in dr.async_get(hass).devices.values():
        # Services such as Sun or Backup are not hardware that gets replaced.
        if device.disabled_by or device.entry_type is dr.DeviceEntryType.SERVICE:
            continue
        entries = er.async_entries_for_device(ent_reg, device.id)
        if not entries:
            continue
        states = [hass.states.get(e.entity_id) for e in entries]
        identify = next(
            (
                e.entity_id
                for e in entries
                if e.domain == "button"
                and (e.device_class or e.original_device_class) == "identify"
                and not e.disabled_by
            ),
            None,
        )
        devices.append(
            {
                "id": device.id,
                "name": device.name_by_user or device.name or device.id,
                "manufacturer": device.manufacturer,
                "model": device.model,
                "area_id": device.area_id,
                "integration": _integration_name(hass, device.config_entry_id),
                "created_at": device.created_at.isoformat(),
                "available": any(
                    s is not None and s.state != STATE_UNAVAILABLE for s in states
                ),
                "identify": identify,
            }
        )
    connection.send_result(msg["id"], devices)


@websocket_api.websocket_command({vol.Required("type"): "nine_lives/removed_devices"})
@websocket_api.require_admin
@callback
def ws_removed_devices(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Devices already removed from Home Assistant whose entities can be taken over."""
    connection.send_result(
        msg["id"],
        [
            {
                "id": d.id,
                "name": d.name,
                "removed_at": d.removed_at,
                "area_id": d.area_id,
                "entities": [e.entity_id for e in d.entities],
            }
            for d in deleted.removed_devices(hass)
        ],
    )
