"""Swaps from a device that is already gone from Home Assistant.

A common order of events: the old device is removed in the manufacturer's app or
bridge first, which removes it from Home Assistant too. Home Assistant keeps the removed
entities as "deleted entities", with their entity ID, registry ID and settings, but
without a link to their device. The removed device is kept as well, with little more
than its ID.

Device and entities are removed in the same moment, so the entities of a removed device
are found by their integration and the time they were removed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.history import get_last_state_changes
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .matching import EntityInfo

# Entities removed this close to their device count as belonging to it.
SAME_REMOVAL_SECONDS = 120


@dataclass
class RemovedDevice:
    """A device removed from Home Assistant, with the entities removed along with it."""

    id: str
    name: str
    removed_at: str
    area_id: str | None
    labels: list[str]
    entities: list[er.DeletedRegistryEntry]


def deleted_entity(
    ent_reg: er.EntityRegistry, entity_id: str
) -> er.DeletedRegistryEntry | None:
    """The deleted entry with this entity ID, if the ID is not in use again."""
    if ent_reg.async_get(entity_id):
        return None
    for entry in ent_reg.deleted_entities.values():
        if entry.entity_id == entity_id:
            return entry
    return None


def _name(
    device: dr.DeletedDeviceEntry, entities: list[er.DeletedRegistryEntry]
) -> str:
    if device.name_by_user:
        return device.name_by_user
    # Without a stored name, the entity IDs are the best hint: light.living_room_2
    names = sorted(e.entity_id.split(".", 1)[1] for e in entities)
    return ", ".join(names[:3]) + (" …" if len(names) > 3 else "")


def _identifier_patterns(device: dr.DeletedDeviceEntry) -> list[re.Pattern[str]]:
    """Patterns for the device's identifiers as they appear in its entities' unique IDs.

    Many integrations build unique IDs from the device identifier: Matter's
    "deviceid_ABC-0C-45" turns up as "ABC-0C-45-45-MatterLight-6-0".
    """
    tokens = set()
    for _, value in device.identifiers:
        value = str(value)
        tokens.add(value)
        prefix, _, rest = value.partition("_")
        if rest and prefix.isalpha():
            tokens.add(rest)
    return [
        re.compile(rf"(?<![A-Za-z0-9]){re.escape(t)}(?![A-Za-z0-9])")
        for t in tokens
        if len(t) >= 6
    ]


def removed_devices(hass: HomeAssistant) -> list[RemovedDevice]:
    """Removed devices whose entities can still be taken over, most recent first.

    An entity belongs to a removed device when its unique ID contains one of the
    device's identifiers. Without such a hint, entities of the same integration that
    were removed in the same moment as the device count; if several devices were
    removed together, that is only a guess, so the hint wins whenever it exists.
    """
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    result = []
    for device in dev_reg.deleted_devices.values():
        candidates = [
            e
            for e in ent_reg.deleted_entities.values()
            if e.config_entry_id == device.config_entry_id
            and abs((e.modified_at - device.modified_at).total_seconds())
            <= SAME_REMOVAL_SECONDS
            and not ent_reg.async_get(e.entity_id)
            and hass.states.get(e.entity_id) is None
        ]
        patterns = _identifier_patterns(device)
        matched = [
            e for e in candidates if any(p.search(e.unique_id) for p in patterns)
        ]
        entities = matched or candidates
        if not entities:
            continue
        result.append(
            RemovedDevice(
                id=device.id,
                name=_name(device, entities),
                removed_at=dt_util.as_utc(device.modified_at).isoformat(),
                area_id=device.area_id,
                labels=sorted(device.labels),
                entities=sorted(entities, key=lambda e: e.entity_id),
            )
        )
    return sorted(result, key=lambda d: d.removed_at, reverse=True)


def removed_device(hass: HomeAssistant, device_id: str) -> RemovedDevice | None:
    return next((d for d in removed_devices(hass) if d.id == device_id), None)


async def async_last_states(
    hass: HomeAssistant, entity_ids: list[str]
) -> dict[str, State]:
    """The last real state the recorder kept for each removed entity.

    Removed entries keep no device class or unit, but their last recorded state does,
    together with the name and the last value.
    """
    if not entity_ids or "recorder" not in hass.config.components:
        return {}

    def _get() -> dict[str, State]:
        result = {}
        for entity_id in entity_ids:
            states = get_last_state_changes(hass, 10, entity_id).get(entity_id, [])
            real = [
                s
                for s in states
                if s.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN) and s.attributes
            ]
            if real:
                result[entity_id] = real[-1]
        return result

    return await get_instance(hass).async_add_executor_job(_get)


def entity_infos(device: RemovedDevice, last: dict[str, State]) -> list[EntityInfo]:
    """What the pairing needs, from the removed entries and their last states."""
    infos = []
    for entry in device.entities:
        attrs = last[entry.entity_id].attributes if entry.entity_id in last else {}
        infos.append(
            EntityInfo(
                entity_id=entry.entity_id,
                registry_id=entry.id,
                device_class=entry.device_class or attrs.get("device_class"),
                unit=attrs.get("unit_of_measurement"),
                state_class=attrs.get("state_class"),
                name=entry.name or attrs.get("friendly_name"),
            )
        )
    return infos


def snapshot(entry: er.DeletedRegistryEntry) -> dict[str, Any]:
    """The settings stored with a deleted entry, like a backup of a live one."""
    options = entry.options if isinstance(entry.options, dict) else {}
    return {
        "entity_id": entry.entity_id,
        "platform": entry.platform,
        "unique_id": entry.unique_id,
        "config_entry_id": entry.config_entry_id,
        "name": entry.name,
        "icon": entry.icon,
        "area_id": entry.area_id,
        "labels": sorted(entry.labels),
        "aliases": [None if a is er.COMPUTED_NAME else a for a in entry.aliases],
        "options": {domain: dict(opts) for domain, opts in options.items()},
    }
