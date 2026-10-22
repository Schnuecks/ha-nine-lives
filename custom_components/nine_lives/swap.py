"""Plan, apply and undo a device swap.

The new entities take over the entity IDs of the old ones, so everything that refers
to an entity ID (automations, dashboards, templates, history) keeps working. To keep
the history continuous, the old registry entries are removed before the new entities
are renamed: the recorder then leaves the old history under the ID and the new entity
continues it. Home Assistant keeps removed entries as "deleted entities", so when the
old integration creates them again, they come back with their registry ID and settings,
which is what undo relies on.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from homeassistant.config import (
    AUTOMATION_CONFIG_PATH,
    SCENE_CONFIG_PATH,
    SCRIPT_CONFIG_PATH,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import (
    async_call_later,
    async_track_point_in_utc_time,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util.file import write_utf8_file_atomic
from homeassistant.util.yaml import dump, parse_yaml

from . import energy
from .const import DOMAIN
from .references import Change, Review, rewrite

CONFIG_FILES = {
    "automation": AUTOMATION_CONFIG_PATH,
    "script": SCRIPT_CONFIG_PATH,
    "scene": SCENE_CONFIG_PATH,
}
# YAML tags such as !secret or !include: loading and dumping would inline their values.
_YAML_TAG = re.compile(r"(?:^|[\s:\[,-])!\w")

_LOGGER = logging.getLogger(__name__)
# The recorder logs that it cannot move the new entity's history onto the taken-over
# ID. That is intended (the old history stays there), so these messages are hidden.
_RECORDER_LOGGERS = (
    "homeassistant.components.recorder.entity_registry",
    "homeassistant.components.recorder.table_managers.statistics_meta",
)
_FILTER_SECONDS = 120

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.backups"


class SwapError(HomeAssistantError):
    """The swap cannot be planned or applied."""


@dataclass
class FilePlan:
    """What happens to one of the config files."""

    kind: str
    path: str
    original: str
    new_text: str | None = None
    changes: list[Change] = field(default_factory=list)
    reviews: list[Review] = field(default_factory=list)
    blocked: str | None = None


@dataclass
class Plan:
    """Everything a swap will change, shown as preview before it is applied."""

    old_device_id: str
    new_device_id: str
    pairs: list[tuple[str, str]]
    id_map: dict[str, str]
    files: list[FilePlan]

    def as_dict(self) -> dict[str, Any]:
        return {
            "old_device_id": self.old_device_id,
            "new_device_id": self.new_device_id,
            "pairs": [{"old": o, "new": n} for o, n in self.pairs],
            "files": [
                {
                    "kind": f.kind,
                    "changes": [asdict(c) for c in f.changes],
                    "reviews": [asdict(r) for r in f.reviews],
                    "blocked": f.blocked,
                }
                for f in self.files
            ],
        }


def _item_label(kind: str, data: Any, key: Any) -> str:
    """A readable name for one automation, script or scene."""
    if isinstance(data, dict):
        name = data.get("alias") or data.get("name") or data.get("id")
        if name:
            return f"{kind} '{name}'"
    return f"{kind} {key}"


def _plan_file(
    kind: str,
    path: str,
    text: str,
    id_map: dict[str, str],
    entity_domains: dict[str, str],
    new_integrations: set[str],
) -> FilePlan:
    plan = FilePlan(kind, path, text)
    if not any(old_id in text for old_id in id_map):
        return plan
    if _YAML_TAG.search(text):
        plan.blocked = "uses YAML tags such as !secret or !include, edit it by hand"
        return plan

    data = parse_yaml(text)
    items = data.items() if isinstance(data, dict) else enumerate(data or [])
    new_data: dict | list = {} if isinstance(data, dict) else []
    for key, item in items:
        result = rewrite(item, id_map, entity_domains, new_integrations)
        label = _item_label(kind, item, key)
        plan.changes += [
            Change(f"{label}: {c.path}", c.old, c.new) for c in result.changes
        ]
        plan.reviews += [Review(f"{label}: {r.path}", r.reason) for r in result.reviews]
        if isinstance(new_data, dict):
            new_data[key] = result.config
        else:
            new_data.append(result.config)
    if plan.changes:
        plan.new_text = dump(new_data)
    return plan


def _read(path: str) -> str | None:
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as file:
        return file.read()


async def async_plan(
    hass: HomeAssistant,
    old_device_id: str,
    new_device_id: str,
    pairs: list[tuple[str, str]],
) -> Plan:
    """Check the request and work out every change, without changing anything."""
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    if old_device_id == new_device_id:
        raise SwapError("Old and new device are the same")
    if not dev_reg.async_get(old_device_id) or not dev_reg.async_get(new_device_id):
        raise SwapError("Device not found")
    if not pairs:
        raise SwapError("No entities to swap")
    olds = [o for o, _ in pairs]
    news = [n for _, n in pairs]
    if len(set(olds)) != len(olds) or len(set(news)) != len(news):
        raise SwapError("Every entity may only be used once")

    id_map = {old_device_id: new_device_id}
    entity_domains: dict[str, str] = {}
    for old, new in pairs:
        old_entry = ent_reg.async_get(old)
        new_entry = ent_reg.async_get(new)
        if not old_entry or old_entry.device_id != old_device_id:
            raise SwapError(f"{old} does not belong to the old device")
        if not new_entry or new_entry.device_id != new_device_id:
            raise SwapError(f"{new} does not belong to the new device")
        if old_entry.domain != new_entry.domain:
            raise SwapError(f"{old} and {new} are of different types")
        id_map[old_entry.id] = new_entry.id
        entity_domains[new_entry.id] = new_entry.domain

    new_device = dev_reg.async_get(new_device_id)
    new_integrations = set()
    if new_device and new_device.config_entry_id:
        entry = hass.config_entries.async_get_entry(new_device.config_entry_id)
        if entry:
            new_integrations.add(entry.domain)

    files = []
    for kind, name in CONFIG_FILES.items():
        path = hass.config.path(name)
        text = await hass.async_add_executor_job(_read, path)
        if text is not None:
            files.append(
                _plan_file(kind, path, text, id_map, entity_domains, new_integrations)
            )
    return Plan(old_device_id, new_device_id, pairs, id_map, files)


def _entity_snapshot(entry: er.RegistryEntry) -> dict[str, Any]:
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
        "options": {domain: dict(opts) for domain, opts in entry.options.items()},
    }


def _restore_customizations(
    ent_reg: er.EntityRegistry, entity_id: str, snap: dict[str, Any]
) -> None:
    ent_reg.async_update_entity(
        entity_id,
        name=snap["name"],
        icon=snap["icon"],
        area_id=snap["area_id"],
        labels=set(snap["labels"]),
        aliases=[er.COMPUTED_NAME if a is None else a for a in snap["aliases"]],
    )
    current = ent_reg.async_get(entity_id)
    for domain in set(current.options if current else {}) - set(snap["options"]):
        ent_reg.async_update_entity_options(entity_id, domain, None)
    for domain, options in snap["options"].items():
        ent_reg.async_update_entity_options(entity_id, domain, options)


def _copy_customizations(
    ent_reg: er.EntityRegistry, old: er.RegistryEntry, new_entity_id: str
) -> None:
    """Give the new entity what the user set on the old one."""
    ent_reg.async_update_entity(
        new_entity_id,
        name=old.name,
        icon=old.icon,
        area_id=old.area_id,
        labels=set(old.labels),
        aliases=list(old.aliases),
    )
    for domain, options in old.options.items():
        ent_reg.async_update_entity_options(new_entity_id, domain, dict(options))


async def _async_write_files(
    hass: HomeAssistant, texts: dict[str, tuple[str, str]]
) -> None:
    """Write the given files and reload the matching integrations."""
    for kind, (path, text) in texts.items():
        await hass.async_add_executor_job(write_utf8_file_atomic, path, text)
        if hass.services.has_service(kind, "reload"):
            await hass.services.async_call(kind, "reload", blocking=True)


class _ExpectedRenameFilter(logging.Filter):
    """Drop the recorder's rename messages for the entity pairs of one swap."""

    def __init__(self, renames: set[tuple[str, str]]) -> None:
        super().__init__()
        self.renames = renames

    def filter(self, record: logging.LogRecord) -> bool:
        return not (isinstance(record.args, tuple) and record.args in self.renames)


def _hide_expected_recorder_messages(
    hass: HomeAssistant, renames: set[tuple[str, str]]
) -> Callable[[], None]:
    log_filter = _ExpectedRenameFilter(renames)
    loggers = [logging.getLogger(name) for name in _RECORDER_LOGGERS]
    for logger in loggers:
        logger.addFilter(log_filter)

    @callback
    def _remove(_now: Any) -> None:
        for logger in loggers:
            logger.removeFilter(log_filter)

    cancel_timer = async_call_later(hass, _FILTER_SECONDS, _remove)

    @callback
    def _remove_now() -> None:
        cancel_timer()
        _remove(None)

    return _remove_now


def _free_entity_id(hass: HomeAssistant, entity_id: str) -> None:
    """Drop a leftover state so the ID can be taken over right away."""
    if hass.states.get(entity_id) is not None:
        hass.states.async_remove(entity_id)


class SwapManager:
    """Applies swaps and keeps the backups needed to undo them."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.backups: dict[str, dict[str, Any]] = {}
        # Meter sum corrections waiting for the recorder to compile their period.
        self.pending: list[dict[str, Any]] = []
        self._unsubs: list[Any] = []

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self.backups = data.get("backups", {})
        self.pending = data.get("pending", [])
        for item in self.pending:
            self._schedule(item, energy.next_check(item))

    @callback
    def async_unload(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    async def _async_save(self) -> None:
        await self._store.async_save({"backups": self.backups, "pending": self.pending})

    async def _async_add_corrections(
        self, handovers: list[tuple[str, Any, Any]]
    ) -> None:
        """Queue sum corrections for meters handing over (statistic, before, after)."""
        if "recorder" not in self.hass.config.components:
            return
        now = dt_util.utcnow()
        for statistic_id, before, after in handovers:
            item = energy.pending_adjustment(statistic_id, before, after, now)
            if item:
                self.pending.append(item)
                self._schedule(item, energy.next_check(item))
        await self._async_save()

    @callback
    def _schedule(self, item: dict[str, Any], when: Any) -> None:
        async def _run(_now: Any) -> None:
            self._unsubs.remove(unsub)
            if item not in self.pending:
                return
            result = await energy.async_try_apply(self.hass, item)
            if result is False:
                self._schedule(item, dt_util.utcnow() + energy.RETRY_DELAY)
                return
            self.pending.remove(item)
            await self._async_save()

        unsub = async_track_point_in_utc_time(
            self.hass, _run, max(when, dt_util.utcnow())
        )
        self._unsubs.append(unsub)

    async def async_apply(self, plan: Plan) -> str:
        """Apply a plan and return the ID of its backup."""
        hass = self.hass
        ent_reg = er.async_get(hass)
        dev_reg = dr.async_get(hass)
        old_device = dev_reg.async_get(plan.old_device_id)
        new_device = dev_reg.async_get(plan.new_device_id)
        if old_device is None or new_device is None:
            raise SwapError("Device not found")

        backup_id = uuid.uuid4().hex
        self.backups[backup_id] = {
            "created": dt_util.utcnow().isoformat(),
            "old_device": {
                "id": old_device.id,
                "name": old_device.name_by_user or old_device.name,
                "disabled_by": old_device.disabled_by,
            },
            "new_device": {
                "id": new_device.id,
                "name": new_device.name_by_user or new_device.name,
                "area_id": new_device.area_id,
                "labels": sorted(new_device.labels),
            },
            "pairs": [
                {
                    "old": _entity_snapshot(ent_reg.async_get(old)),
                    "new": _entity_snapshot(ent_reg.async_get(new)),
                }
                for old, new in plan.pairs
            ],
            "id_map": plan.id_map,
            "files": {
                f.kind: {"path": f.path, "text": f.original, "written": f.new_text}
                for f in plan.files
                if f.new_text is not None
            },
        }
        await self._async_save()

        # The new meters continue the old meters' sums from here on. An old meter
        # that is unavailable hands over the reading the recorder compiled last.
        handovers = []
        for old_id, new_id in plan.pairs:
            before = hass.states.get(old_id)
            if energy.state_value(before) is None:
                capabilities = ent_reg.async_get(old_id).capabilities or {}
                before = await energy.async_last_known_state(
                    hass, old_id, capabilities.get("state_class")
                )
            handovers.append((old_id, before, hass.states.get(new_id)))

        # Entities: customizations over, old entry out, new entity takes the old ID.
        self._unsubs.append(
            _hide_expected_recorder_messages(hass, {(n, o) for o, n in plan.pairs})
        )
        for old_id, new_id in plan.pairs:
            old_entry = ent_reg.async_get(old_id)
            _copy_customizations(ent_reg, old_entry, new_id)
            ent_reg.async_remove(old_id)
            _free_entity_id(hass, old_id)
            _free_entity_id(hass, new_id)
            ent_reg.async_update_entity(new_id, new_entity_id=old_id)
            _LOGGER.info("%s now continues %s", new_id, old_id)

        # Devices: area and labels to the new one, the old one is switched off.
        dev_reg.async_update_device(
            new_device.id,
            area_id=new_device.area_id or old_device.area_id,
            labels=set(new_device.labels) | set(old_device.labels),
        )
        if old_device.disabled_by is None:
            dev_reg.async_update_device(
                old_device.id, disabled_by=dr.DeviceEntryDisabler.USER
            )

        await _async_write_files(
            hass,
            {f.kind: (f.path, f.new_text) for f in plan.files if f.new_text},
        )
        await self._async_add_corrections(handovers)
        return backup_id

    async def async_undo(self, backup_id: str) -> list[str]:
        """Put everything back as it was before the swap; return notes for the user."""
        hass = self.hass
        notes: list[str] = []
        backup = self.backups.get(backup_id)
        if backup is None:
            raise SwapError("Backup not found")
        ent_reg = er.async_get(hass)
        dev_reg = dr.async_get(hass)
        last_states = {
            p["old"]["entity_id"]: hass.states.get(p["old"]["entity_id"])
            for p in backup["pairs"]
        }

        # Undoing moves IDs back, which the recorder again reports as collisions.
        self._unsubs.append(
            _hide_expected_recorder_messages(
                hass,
                {
                    (p["old"]["entity_id"], p["new"]["entity_id"])
                    for p in backup["pairs"]
                },
            )
        )

        # New entities back to their own IDs and settings.
        for pair in backup["pairs"]:
            old, new = pair["old"], pair["new"]
            current = ent_reg.async_get_entity_id(
                new["entity_id"].split(".", 1)[0], new["platform"], new["unique_id"]
            )
            if current is None:
                continue
            if current != new["entity_id"]:
                _free_entity_id(hass, current)
                ent_reg.async_update_entity(current, new_entity_id=new["entity_id"])
            _restore_customizations(ent_reg, new["entity_id"], new)

        new_device = backup["new_device"]
        if dev_reg.async_get(new_device["id"]):
            dev_reg.async_update_device(
                new_device["id"],
                area_id=new_device["area_id"],
                labels=set(new_device["labels"]),
            )

        # Old device back on. If its integration already created the old entities
        # again (after a restart), they get their IDs back; otherwise reloading the
        # integration restores them from the deleted entities.
        old_device = backup["old_device"]
        reload_entries: set[str] = set()
        if dev_reg.async_get(old_device["id"]):
            disabled_by = old_device["disabled_by"]
            dev_reg.async_update_device(
                old_device["id"],
                disabled_by=dr.DeviceEntryDisabler(disabled_by)
                if disabled_by
                else None,
            )
        for pair in backup["pairs"]:
            old = pair["old"]
            domain = old["entity_id"].split(".", 1)[0]
            current = ent_reg.async_get_entity_id(
                domain, old["platform"], old["unique_id"]
            )
            if current is None:
                if old["config_entry_id"]:
                    reload_entries.add(old["config_entry_id"])
                continue
            if current != old["entity_id"]:
                _free_entity_id(hass, current)
                ent_reg.async_update_entity(current, new_entity_id=old["entity_id"])
            _restore_customizations(ent_reg, old["entity_id"], old)
        # The old entities must exist again before automations referring to them load.
        for entry_id in reload_entries:
            if hass.config_entries.async_get_entry(entry_id):
                await hass.config_entries.async_reload(entry_id)

        # Files untouched since the swap get their old text back. Files edited since
        # then keep those edits and only have the device references turned back.
        texts = {}
        reverse_map = {new: old for old, new in backup["id_map"].items()}
        for kind, f in backup["files"].items():
            current = await hass.async_add_executor_job(_read, f["path"])
            if current is None or current == f["written"]:
                texts[kind] = (f["path"], f["text"])
                continue
            reverted = _plan_file(kind, f["path"], current, reverse_map, {}, set())
            if reverted.blocked:
                notes.append(f"{f['path']} {reverted.blocked}")
            elif reverted.new_text:
                texts[kind] = (f["path"], reverted.new_text)
        await _async_write_files(hass, texts)

        # The old meters take their sums back over from the new ones.
        await self._async_add_corrections(
            [(eid, last, hass.states.get(eid)) for eid, last in last_states.items()]
        )

        del self.backups[backup_id]
        await self._async_save()
        return notes
