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
from homeassistant.core import HomeAssistant, callback, valid_entity_id
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

from . import deleted, energy, notice, scan
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
    dashboards: list[scan.DashboardPlan] = field(default_factory=list)
    reports: list[scan.Report] = field(default_factory=list)
    # Tidier IDs the user chose: old entity ID -> ID the new entity ends up with.
    new_ids: dict[str, str] = field(default_factory=dict)
    # The old device is already removed; the old entities are deleted registry entries.
    from_deleted: bool = False
    # Helpers and the energy dashboard that use an entity whose ID changes.
    settings: list[scan.SettingsPlan] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "old_device_id": self.old_device_id,
            "new_device_id": self.new_device_id,
            "pairs": [
                {"old": o, "new": n, "final": self.new_ids.get(o, o)}
                for o, n in self.pairs
            ],
            "files": [
                {
                    "kind": f.kind,
                    "changes": [asdict(c) for c in f.changes],
                    "reviews": [asdict(r) for r in f.reviews],
                    "blocked": f.blocked,
                }
                for f in self.files
            ]
            + [
                {
                    "kind": "dashboard",
                    "changes": [asdict(c) for c in d.changes],
                    "reviews": [asdict(r) for r in d.reviews],
                    "blocked": None,
                }
                for d in self.dashboards
            ]
            + [
                {
                    "kind": p.kind,
                    "changes": [asdict(c) for c in p.changes],
                    "reviews": [],
                    "blocked": None,
                }
                for p in self.settings
            ],
            "reports": [asdict(r) for r in self.reports],
            "from_deleted": self.from_deleted,
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
    renames: dict[str, str] | None = None,
) -> FilePlan:
    plan = FilePlan(kind, path, text)
    renames = renames or {}
    if not any(old_id in text for old_id in id_map) and not any(
        scan.is_referenced(old, [text]) for old in renames
    ):
        return plan
    if _YAML_TAG.search(text):
        # A code the panel translates: the file uses !secret, !include and the like.
        plan.blocked = "yaml_tags"
        return plan

    data = parse_yaml(text)
    items = data.items() if isinstance(data, dict) else enumerate(data or [])
    new_data: dict | list = {} if isinstance(data, dict) else []
    for key, item in items:
        result = rewrite(item, id_map, entity_domains, new_integrations, renames)
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
    new_ids: dict[str, str] | None = None,
) -> Plan:
    """Check the request and work out every change, without changing anything.

    new_ids optionally gives a tidier ID for some old entity IDs; it is only allowed
    when nothing refers to the old ID.
    """
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    if old_device_id == new_device_id:
        raise SwapError("Old and new device are the same")
    from_deleted = dev_reg.async_get(old_device_id) is None
    if from_deleted and old_device_id not in dev_reg.deleted_devices:
        raise SwapError("Device not found")
    if not dev_reg.async_get(new_device_id):
        raise SwapError("Device not found")
    if not pairs:
        raise SwapError("No entities to swap")
    olds = [o for o, _ in pairs]
    news = [n for _, n in pairs]
    if len(set(olds)) != len(olds) or len(set(news)) != len(news):
        raise SwapError("Every entity may only be used once")

    id_map = {old_device_id: new_device_id}
    entity_domains: dict[str, str] = {}
    removed = deleted.removed_device(hass, old_device_id) if from_deleted else None
    for old, new in pairs:
        new_entry = ent_reg.async_get(new)
        if from_deleted:
            old_entry = deleted.deleted_entity(ent_reg, old)
            if not removed or old_entry not in removed.entities:
                raise SwapError(f"{old} does not belong to the old device")
        else:
            old_entry = ent_reg.async_get(old)
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

    new_ids = await _async_check_new_ids(hass, olds, news, new_ids or {})
    files = []
    for kind, name in CONFIG_FILES.items():
        path = hass.config.path(name)
        text = await hass.async_add_executor_job(_read, path)
        if text is not None:
            files.append(
                _plan_file(
                    kind, path, text, id_map, entity_domains, new_integrations, new_ids
                )
            )
    dashboards, reports = await scan.async_plan_dashboards(
        hass, id_map, entity_domains, new_integrations, new_ids
    )
    reports += await scan.async_yaml_reports(hass, id_map)
    settings, setting_reports = await scan.async_plan_settings(hass, new_ids)
    reports += setting_reports
    return Plan(
        old_device_id,
        new_device_id,
        pairs,
        id_map,
        files,
        dashboards,
        reports,
        new_ids,
        from_deleted,
        settings,
    )


async def _async_check_new_ids(
    hass: HomeAssistant, olds: list[str], news: list[str], new_ids: dict[str, str]
) -> dict[str, str]:
    """Only unused old IDs may change, and only to a free ID of the same type."""
    new_ids = {old: new for old, new in new_ids.items() if new and new != old}
    if not new_ids:
        return {}
    ent_reg = er.async_get(hass)
    usage = await scan.async_entity_usage(hass, list(new_ids))
    targets = list(new_ids.values())
    for old, target in new_ids.items():
        if old not in olds:
            raise SwapError(f"{old} is not swapped")
        if not valid_entity_id(target) or target.split(".")[0] != old.split(".")[0]:
            raise SwapError(f"{target} is not a valid ID for {old}")
        if targets.count(target) > 1 or target in olds:
            raise SwapError(f"{target} is used twice")
        taken = ent_reg.async_get(target) or hass.states.get(target)
        if taken and target not in news:
            raise SwapError(f"{target} is already taken")
        # Places Nine Lives cannot adjust keep the ID from changing.
        if blocked := usage[old][1]:
            raise SwapError(
                f"{old} is used in {', '.join(blocked)}, its ID cannot change there"
            )
    return new_ids


async def async_suggest_ids(
    hass: HomeAssistant, entity_ids: list[str]
) -> dict[str, dict[str, Any]]:
    """Tidier IDs for old entities whose ID no longer matches their name.

    Offered when the tidier ID is free and every place using the old ID can be
    adjusted; used_in lists those places, so the panel can say what changes along.
    """
    ent_reg = er.async_get(hass)
    candidates = {}
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        name = state.attributes.get("friendly_name") if state else None
        suggestion = scan.suggested_entity_id(entity_id, name)
        if suggestion and not ent_reg.async_get(suggestion):
            candidates[entity_id] = suggestion
    if not candidates:
        return {}
    usage = await scan.async_entity_usage(hass, list(candidates))
    return {
        old: {"id": new, "used_in": usage[old][0]}
        for old, new in candidates.items()
        if not usage[old][1]
    }


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
    ent_reg: er.EntityRegistry, old: dict[str, Any], new_entity_id: str
) -> None:
    """Give the new entity what the user set on the old one (a snapshot of it)."""
    ent_reg.async_update_entity(
        new_entity_id,
        name=old["name"],
        icon=old["icon"],
        area_id=old["area_id"],
        labels=set(old["labels"]),
        aliases=[er.COMPUTED_NAME if a is None else a for a in old["aliases"]],
    )
    for domain, options in old["options"].items():
        ent_reg.async_update_entity_options(new_entity_id, domain, dict(options))


async def _async_write_files(
    hass: HomeAssistant, texts: dict[str, tuple[str, str]]
) -> None:
    """Write the given files and reload the matching integrations."""
    for kind, (path, text) in texts.items():
        await hass.async_add_executor_job(write_utf8_file_atomic, path, text)
        if hass.services.has_service(kind, "reload"):
            await hass.services.async_call(kind, "reload", blocking=True)


async def _async_current_dashboard(
    hass: HomeAssistant, url_path: str | None
) -> dict[str, Any] | None:
    for dashboard, config in await scan.async_dashboards(hass):
        if dashboard.url_path == url_path:
            return config
    return None


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


def _history_entry(backup: dict[str, Any], plan: Plan | None = None) -> dict[str, Any]:
    """What a swap did, in a form the panel can show later."""
    new_ids = backup.get("new_ids", {})
    entry: dict[str, Any] = {
        "created": backup["created"],
        "old_device": backup["old_device"]["name"],
        "new_device": backup["new_device"]["name"],
        "pairs": [
            {
                "old": p["old"]["entity_id"],
                "new": p["new"]["entity_id"],
                "final": new_ids.get(p["old"]["entity_id"], p["old"]["entity_id"]),
            }
            for p in backup["pairs"]
        ],
        "changes": [],
        "reviews": [],
        "reports": [],
        "corrections": [],
        "undone": None,
        "notes": [],
        "from_deleted": bool(backup["old_device"].get("removed")),
    }
    if plan is not None:
        details = plan.as_dict()
        entry["changes"] = [c["path"] for f in details["files"] for c in f["changes"]]
        entry["reviews"] = [r for f in details["files"] for r in f["reviews"]]
        entry["reports"] = details["reports"] + [
            {"where": f["kind"], "reason": f["blocked"]}
            for f in details["files"]
            if f["blocked"]
        ]
    return entry


class SwapManager:
    """Applies swaps and keeps the backups needed to undo them."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.backups: dict[str, dict[str, Any]] = {}
        # What each swap did, kept after an undo as well so it stays traceable.
        self.history: dict[str, dict[str, Any]] = {}
        # Meter sum corrections waiting for the recorder to compile their period.
        self.pending: list[dict[str, Any]] = []
        self._unsubs: list[Any] = []

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self.backups = data.get("backups", {})
        self.history = data.get("history", {})
        self.pending = data.get("pending", [])
        # Swaps made before the history existed: what the backup still tells.
        for swap_id, backup in self.backups.items():
            self.history.setdefault(swap_id, _history_entry(backup))
        for item in self.pending:
            self._schedule(item, energy.next_check(item))

    @callback
    def async_unload(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    async def _async_save(self) -> None:
        await self._store.async_save(
            {"backups": self.backups, "history": self.history, "pending": self.pending}
        )

    async def _async_add_corrections(
        self, handovers: list[tuple[str, Any, Any]], swap_id: str, phase: str
    ) -> None:
        """Queue sum corrections for meters handing over (statistic, before, after).

        phase is "swap" or "undo"; the swap's history lists each correction.
        """
        if "recorder" not in self.hass.config.components:
            return
        now = dt_util.utcnow()
        for statistic_id, before, after in handovers:
            item = energy.pending_adjustment(statistic_id, before, after, now)
            if item:
                item["id"] = uuid.uuid4().hex
                item["swap_id"] = swap_id
                self.pending.append(item)
                if entry := self.history.get(swap_id):
                    entry.setdefault("corrections", []).append(
                        {
                            "id": item["id"],
                            "phase": phase,
                            "statistic_id": statistic_id,
                            "adjustment": item["adjustment"],
                            "unit": item["unit"],
                            "status": "pending",
                        }
                    )
                self._schedule(item, energy.next_check(item))
        await self._async_save()

    def _mark_correction(self, item: dict[str, Any], status: str) -> None:
        entry = self.history.get(item.get("swap_id", ""))
        for correction in (entry or {}).get("corrections", []):
            if correction["id"] == item.get("id"):
                correction["status"] = status

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
            self._mark_correction(item, "applied" if result else "failed")
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
        new_device = dev_reg.async_get(plan.new_device_id)
        if plan.from_deleted:
            removed = deleted.removed_device(hass, plan.old_device_id)
            old_device = None
            if removed is None or new_device is None:
                raise SwapError("Device not found")
            old_info = {
                "id": removed.id,
                "name": removed.name,
                "disabled_by": None,
                "removed": True,
            }
            old_area, old_labels = removed.area_id, set(removed.labels)
            old_snapshots = {
                old: deleted.snapshot(deleted.deleted_entity(ent_reg, old))
                for old, _ in plan.pairs
            }
        else:
            old_device = dev_reg.async_get(plan.old_device_id)
            if old_device is None or new_device is None:
                raise SwapError("Device not found")
            old_info = {
                "id": old_device.id,
                "name": old_device.name_by_user or old_device.name,
                "disabled_by": old_device.disabled_by,
            }
            old_area, old_labels = old_device.area_id, set(old_device.labels)
            old_snapshots = {
                old: _entity_snapshot(ent_reg.async_get(old)) for old, _ in plan.pairs
            }

        backup_id = uuid.uuid4().hex
        self.backups[backup_id] = {
            "created": dt_util.utcnow().isoformat(),
            "old_device": old_info,
            "new_device": {
                "id": new_device.id,
                "name": new_device.name_by_user or new_device.name,
                "area_id": new_device.area_id,
                "labels": sorted(new_device.labels),
            },
            "pairs": [
                {
                    "old": old_snapshots[old],
                    "new": _entity_snapshot(ent_reg.async_get(new)),
                }
                for old, new in plan.pairs
            ],
            "id_map": plan.id_map,
            "new_ids": plan.new_ids,
            "dashboards": [
                {"url_path": d.url_path, "text": d.original, "written": d.new_config}
                for d in plan.dashboards
                if d.new_config is not None
            ],
            "files": {
                f.kind: {"path": f.path, "text": f.original, "written": f.new_text}
                for f in plan.files
                if f.new_text is not None
            },
            "settings": [
                {"kind": p.kind, "key": p.key, "text": p.original, "written": p.new}
                for p in plan.settings
            ],
        }
        self.history[backup_id] = _history_entry(self.backups[backup_id], plan)
        await self._async_save()

        # The new meters continue the old meters' sums from here on. An old meter
        # that is unavailable hands over the reading the recorder compiled last.
        handovers = []
        for old_id, new_id in plan.pairs:
            before = hass.states.get(old_id)
            if energy.state_value(before) is None:
                # A removed entity keeps no capabilities; its successor has the same.
                live = ent_reg.async_get(old_id)
                after = hass.states.get(new_id)
                state_class = (
                    (live.capabilities or {}).get("state_class")
                    if live
                    else after.attributes.get("state_class")
                    if after
                    else None
                )
                before = await energy.async_last_known_state(hass, old_id, state_class)
            handovers.append(
                (plan.new_ids.get(old_id, old_id), before, hass.states.get(new_id))
            )

        # Entities: customizations over, old entry out, new entity takes the old ID.
        self._unsubs.append(
            _hide_expected_recorder_messages(hass, {(n, o) for o, n in plan.pairs})
        )
        for old_id, new_id in plan.pairs:
            _copy_customizations(ent_reg, old_snapshots[old_id], new_id)
            if not plan.from_deleted:
                ent_reg.async_remove(old_id)
            _free_entity_id(hass, old_id)
            _free_entity_id(hass, new_id)
            ent_reg.async_update_entity(new_id, new_entity_id=old_id)
            _LOGGER.info("%s now continues %s", new_id, old_id)
            # A tidier ID, chosen by the user: history and statistics move along.
            if target := plan.new_ids.get(old_id):
                _free_entity_id(hass, old_id)
                ent_reg.async_update_entity(old_id, new_entity_id=target)

        # Devices: area and labels to the new one, the old one is switched off.
        dev_reg.async_update_device(
            new_device.id,
            area_id=new_device.area_id or old_area,
            labels=set(new_device.labels) | old_labels,
        )
        if old_device is not None and old_device.disabled_by is None:
            dev_reg.async_update_device(
                old_device.id, disabled_by=dr.DeviceEntryDisabler.USER
            )

        await _async_write_files(
            hass,
            {f.kind: (f.path, f.new_text) for f in plan.files if f.new_text},
        )
        for dashboard in plan.dashboards:
            if dashboard.new_config is not None:
                await scan.async_save_dashboard(
                    hass, dashboard.url_path, dashboard.new_config
                )
        for settings in plan.settings:
            await scan.async_apply_settings(hass, settings)
        await self._async_add_corrections(handovers, backup_id, "swap")
        notice.async_swapped(
            hass,
            backup_id,
            old_info["name"] or old_info["id"],
            new_device.name_by_user or new_device.name or new_device.id,
            len(plan.pairs),
            [r.where for r in plan.reports] + [f.path for f in plan.files if f.blocked],
        )
        return backup_id

    def old_device_removed(self, swap_id: str) -> bool:
        """Whether the old device of a swap is gone from Home Assistant."""
        backup = self.backups.get(swap_id)
        if backup is None:
            return False
        return dr.async_get(self.hass).async_get(backup["old_device"]["id"]) is None

    def can_undo(self, swap_id: str) -> bool:
        """Undo needs the backup and the old device: without it, it could not return."""
        entry = self.history.get(swap_id, {})
        return (
            swap_id in self.backups
            and not entry.get("undone")
            and not self.old_device_removed(swap_id)
        )

    async def async_undo(self, backup_id: str) -> list[str]:
        """Put everything back as it was before the swap; return notes for the user."""
        hass = self.hass
        notes: list[str] = []
        backup = self.backups.get(backup_id)
        if backup is None:
            raise SwapError("Backup not found")
        if self.old_device_removed(backup_id):
            raise SwapError("The old device was removed, the swap cannot be undone")
        ent_reg = er.async_get(hass)
        dev_reg = dr.async_get(hass)

        # Where the new entities are now: the old ID, or a tidier one chosen at the
        # swap. A tidier ID goes back to the old ID first, so the old history (which
        # moved along with it) ends up under the old ID again.
        last_states = {}
        for pair in backup["pairs"]:
            old, new = pair["old"], pair["new"]
            current = ent_reg.async_get_entity_id(
                new["entity_id"].split(".", 1)[0], new["platform"], new["unique_id"]
            )
            last_states[old["entity_id"]] = (
                hass.states.get(current) if current else None
            )
            if (
                current
                and current not in (old["entity_id"], new["entity_id"])
                and not ent_reg.async_get(old["entity_id"])
            ):
                _free_entity_id(hass, current)
                ent_reg.async_update_entity(current, new_entity_id=old["entity_id"])

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
        reverse_renames = {new: old for old, new in backup.get("new_ids", {}).items()}
        for kind, f in backup["files"].items():
            current = await hass.async_add_executor_job(_read, f["path"])
            if current is None or current == f["written"]:
                texts[kind] = (f["path"], f["text"])
                continue
            reverted = _plan_file(
                kind, f["path"], current, reverse_map, {}, set(), reverse_renames
            )
            if reverted.blocked:
                notes.append(
                    f"{f['path']} uses YAML tags, turn its device references back"
                    " by hand"
                )
            elif reverted.new_text:
                texts[kind] = (f["path"], reverted.new_text)
        await _async_write_files(hass, texts)

        for dashboard in backup.get("dashboards", []):
            config = await _async_current_dashboard(hass, dashboard["url_path"])
            if config is None:
                continue
            if config == dashboard["written"]:
                restored = dashboard["text"]
            else:
                restored = rewrite(
                    config, reverse_map, entity_renames=reverse_renames
                ).config
            await scan.async_save_dashboard(hass, dashboard["url_path"], restored)

        for saved in backup.get("settings", []):
            current = await scan.async_current_settings(
                hass, saved["kind"], saved["key"]
            )
            if current is None:
                continue
            if current == saved["written"]:
                restored = saved["text"]
            else:
                restored = rewrite(current, {}, entity_renames=reverse_renames).config
            await scan.async_apply_settings(
                hass,
                scan.SettingsPlan(saved["kind"], saved["key"], "", current, restored),
            )

        # The old meters take their sums back over from the new ones.
        if entry := self.history.get(backup_id):
            entry["undone"] = dt_util.utcnow().isoformat()
            entry["notes"] = notes
        await self._async_add_corrections(
            [(eid, last, hass.states.get(eid)) for eid, last in last_states.items()],
            backup_id,
            "undo",
        )

        notice.async_undone(hass, backup_id)
        del self.backups[backup_id]
        await self._async_save()
        return notes
