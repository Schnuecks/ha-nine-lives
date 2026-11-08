"""Integrations that describe a device from the outside, like Battery Notes.

Battery Notes keeps a config subentry per device that points at the device by its
ID; its entities hang on that device and their unique IDs are derived from the
subentry. Swapping the device leaves the note behind on the old device, and the
new device starts without one. A swap therefore points the note at the new device:
its entities keep their IDs, settings and history, and the battery type comes from
Battery Notes' library for the new model. Undo points it back.
"""

from __future__ import annotations

import json
import logging
import os
from types import MappingProxyType
from typing import Any

from homeassistant.config_entries import ConfigEntryState, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

_LOGGER = logging.getLogger(__name__)

BATTERY_NOTES = "battery_notes"
# Their entities belong to the note, not to the device: never paired as entities.
FOLLOWER_PLATFORMS = {BATTERY_NOTES}

_LIBRARY = os.path.join(".storage", "battery_notes", "library.json")


def _note_for(hass: HomeAssistant, device_id: str):
    """The Battery Notes entry and subentry that describe a device, if any."""
    for entry in hass.config_entries.async_entries(BATTERY_NOTES):
        for sub in entry.subentries.values():
            if sub.data.get("device_id") == device_id:
                return entry, sub
    return None, None


def _read_library(path: str) -> list[dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("devices", [])
    except OSError, ValueError:
        return []


def battery_from_library(
    devices: list[dict[str, Any]], device: dr.DeviceEntry
) -> tuple[str, int] | None:
    """Battery type and count for a device, the most specific library match first."""

    def same(a: Any, b: Any) -> bool:
        return str(a or "").casefold() == str(b or "").casefold()

    found = [
        d
        for d in devices
        if same(d.get("manufacturer"), device.manufacturer)
        and same(d.get("model"), device.model)
    ]
    for match in (
        lambda d: (
            same(d.get("model_id"), device.model_id)
            and same(d.get("hw_version"), device.hw_version)
        ),
        lambda d: same(d.get("model_id"), device.model_id) and not d.get("hw_version"),
        lambda d: not d.get("model_id") and not d.get("hw_version"),
    ):
        for d in found:
            if match(d) and d.get("battery_type"):
                return d["battery_type"], int(d.get("battery_quantity") or 1)
    return None


def _move_entities(
    hass: HomeAssistant, sub: ConfigSubentry, old_uid: str, new_uid: str, device_id: str
) -> None:
    ent_reg = er.async_get(hass)
    for entry in list(ent_reg.entities.values()):
        if entry.config_subentry_id != sub.subentry_id:
            continue
        unique_id = entry.unique_id
        if unique_id.startswith(old_uid):
            unique_id = new_uid + unique_id[len(old_uid) :]
        # Disabled only because its device was: it follows the device it moves to.
        disabled = (
            None
            if entry.disabled_by is er.RegistryEntryDisabler.DEVICE
            else entry.disabled_by
        )
        ent_reg.async_update_entity(
            entry.entity_id,
            new_unique_id=unique_id,
            device_id=device_id,
            disabled_by=disabled,
        )


async def _async_reload(hass: HomeAssistant, entry_id: str) -> None:
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is not None and entry.state is ConfigEntryState.LOADED:
        await hass.config_entries.async_reload(entry_id)


def _replaced(hass: HomeAssistant, unique_id: str) -> str | None:
    """When the battery was last replaced, as the note's sensor shows it."""
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", BATTERY_NOTES, f"{unique_id}_battery_last_replaced"
    )
    state = hass.states.get(entity_id) if entity_id else None
    if state is None or state.state in ("unknown", "unavailable", ""):
        return None
    return state.state


async def async_preview(
    hass: HomeAssistant,
    old_device_id: str,
    new_device: dr.DeviceEntry,
    paired: set[str],
) -> list[dict[str, Any]]:
    """What else hangs on the old device: what moves along, what stays behind."""
    out: list[dict[str, Any]] = []
    entry, sub = _note_for(hass, old_device_id)
    ent_reg = er.async_get(hass)
    if entry is not None and sub is not None:
        library = await hass.async_add_executor_job(
            _read_library, hass.config.path(_LIBRARY)
        )
        battery = battery_from_library(library, new_device)
        out.append(
            {
                "integration": BATTERY_NOTES,
                "moves": True,
                "entities": sorted(
                    e.entity_id
                    for e in ent_reg.entities.values()
                    if e.config_subentry_id == sub.subentry_id
                ),
                "battery": f"{battery[1]}× {battery[0]}" if battery else None,
                "replaces_own": _note_for(hass, new_device.id)[1] is not None,
            }
        )
    device = dr.async_get(hass).async_get(old_device_id)
    if device is None:
        return out
    main = (
        hass.config_entries.async_get_entry(device.config_entry_id)
        if device.config_entry_id
        else None
    )
    own = {main.domain} if main else set()
    left: dict[str, list[str]] = {}
    for e in er.async_entries_for_device(ent_reg, old_device_id):
        if e.platform in FOLLOWER_PLATFORMS or e.entity_id in paired:
            continue
        if e.platform not in own:
            left.setdefault(e.platform, []).append(e.entity_id)
    out += [
        {"integration": k, "moves": False, "entities": sorted(v)}
        for k, v in sorted(left.items())
    ]
    return out


async def async_move(
    hass: HomeAssistant, old_device_id: str, new_device: dr.DeviceEntry
) -> dict[str, Any] | None:
    """Point the old device's battery note at the new device; return what undo needs."""
    entry, sub = _note_for(hass, old_device_id)
    if entry is None or sub is None:
        return None
    saved: dict[str, Any] = {
        "entry_id": entry.entry_id,
        "subentry_id": sub.subentry_id,
        "data": dict(sub.data),
        "title": sub.title,
        "unique_id": sub.unique_id,
        "removed": None,
    }
    # A note the new device got on its own (discovered, accepted) has no history yet:
    # the old note takes its place.
    _, own = _note_for(hass, new_device.id)
    if own is not None:
        saved["removed"] = {
            "subentry_id": own.subentry_id,
            "data": dict(own.data),
            "title": own.title,
            "unique_id": own.unique_id,
            "subentry_type": own.subentry_type,
        }
        hass.config_entries.async_remove_subentry(entry, own.subentry_id)

    library = await hass.async_add_executor_job(
        _read_library, hass.config.path(_LIBRARY)
    )
    battery = battery_from_library(library, new_device)
    data = {**sub.data, "device_id": new_device.id}
    if battery:
        data["battery_type"], data["battery_quantity"] = battery
    old_uid = sub.unique_id or f"bn_{old_device_id}"
    new_uid = f"bn_{new_device.id}"
    replaced = _replaced(hass, old_uid)
    _move_entities(hass, sub, old_uid, new_uid, new_device.id)
    hass.config_entries.async_update_subentry(
        entry,
        sub,
        data=data,
        title=new_device.name_by_user or new_device.name or sub.title,
        unique_id=new_uid,
    )
    # Offers to add a note for the new device are answered by now.
    for flow in hass.config_entries.flow.async_progress_by_handler(BATTERY_NOTES):
        if flow.get("context", {}).get("unique_id") == new_uid:
            hass.config_entries.flow.async_abort(flow["flow_id"])
    await _async_reload(hass, entry.entry_id)
    if replaced and hass.services.has_service(BATTERY_NOTES, "set_battery_replaced"):
        await hass.services.async_call(
            BATTERY_NOTES,
            "set_battery_replaced",
            {"device_id": new_device.id, "datetime_replaced": replaced},
            blocking=True,
        )
    _LOGGER.info("Battery note %s now describes %s", sub.title, new_device.id)
    return saved


async def async_restore(hass: HomeAssistant, saved: dict[str, Any] | None) -> None:
    """Undo async_move: the note describes the old device again."""
    if not saved:
        return
    entry = hass.config_entries.async_get_entry(saved["entry_id"])
    sub = entry.subentries.get(saved["subentry_id"]) if entry else None
    if entry is None or sub is None:
        return
    _move_entities(
        hass,
        sub,
        sub.unique_id or "",
        saved["unique_id"] or "",
        saved["data"]["device_id"],
    )
    hass.config_entries.async_update_subentry(
        entry,
        sub,
        data=saved["data"],
        title=saved["title"],
        unique_id=saved["unique_id"],
    )
    if removed := saved.get("removed"):
        hass.config_entries.async_add_subentry(
            entry,
            ConfigSubentry(
                data=MappingProxyType(removed["data"]),
                subentry_id=removed["subentry_id"],
                subentry_type=removed["subentry_type"],
                title=removed["title"],
                unique_id=removed["unique_id"],
            ),
        )
    await _async_reload(hass, entry.entry_id)
