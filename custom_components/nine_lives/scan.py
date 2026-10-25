"""Look beyond automations, scripts and scenes: dashboards, other YAML files and
everything else that may name an entity.

Dashboards stored by Home Assistant are rewritten like automations. YAML files are only
reported, Nine Lives does not edit them. The same sources tell whether an entity ID is
used anywhere, which decides if Nine Lives may offer a tidier ID.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import slugify

from .references import Change, Review, rewrite

_LOGGER = logging.getLogger(__name__)

# Config files Nine Lives handles itself, or that never name entities.
_SKIP_FILES = {"automations.yaml", "scripts.yaml", "scenes.yaml", "secrets.yaml"}
_SKIP_DIRS = {
    ".storage",
    "custom_components",
    "deps",
    "www",
    "tts",
    "backups",
    "blueprints",
    ".cloud",
}


@dataclass
class DashboardPlan:
    """What happens to one dashboard stored by Home Assistant."""

    url_path: str | None
    title: str
    original: dict[str, Any]
    new_config: dict[str, Any] | None = None
    changes: list[Change] = field(default_factory=list)
    reviews: list[Review] = field(default_factory=list)


@dataclass(frozen=True)
class Report:
    """A place that refers to the old device but is left for the user to edit.

    reason is a code the panel translates: yaml_file or yaml_dashboard.
    """

    where: str
    reason: str


def _dashboard_title(url_path: str | None, config: dict[str, Any]) -> str:
    if config.get("title"):
        return config["title"]
    return "Overview" if url_path in (None, "lovelace") else url_path


async def async_dashboards(hass: HomeAssistant) -> list[tuple[Any, dict[str, Any]]]:
    """All dashboards with their current config, skipping empty ones."""
    if LOVELACE_DATA not in hass.data:
        return []
    result = []
    for dashboard in hass.data[LOVELACE_DATA].dashboards.values():
        try:
            config = await dashboard.async_load(False)
        except HomeAssistantError:
            continue
        result.append((dashboard, config))
    return result


async def async_plan_dashboards(
    hass: HomeAssistant,
    id_map: dict[str, str],
    entity_domains: dict[str, str],
    new_integrations: set[str],
    renames: dict[str, str] | None = None,
) -> tuple[list[DashboardPlan], list[Report]]:
    """Rewrite stored dashboards, report YAML dashboards that refer to the device."""
    plans: list[DashboardPlan] = []
    reports: list[Report] = []
    for dashboard, config in await async_dashboards(hass):
        text = json.dumps(config, default=str)
        if not any(old_id in text for old_id in id_map) and not _mentions(
            text, list(renames or {})
        ):
            continue
        title = _dashboard_title(dashboard.url_path, config)
        if dashboard.mode != "storage":
            reports.append(Report(f"dashboard '{title}'", "yaml_dashboard"))
            continue
        result = rewrite(config, id_map, entity_domains, new_integrations, renames)
        plans.append(
            DashboardPlan(
                dashboard.url_path,
                title,
                config,
                result.config if result.changes else None,
                [
                    Change(f"dashboard '{title}': {c.path}", c.old, c.new)
                    for c in result.changes
                ],
                [
                    Review(f"dashboard '{title}': {r.path}", r.reason)
                    for r in result.reviews
                ],
            )
        )
    return plans, reports


async def async_save_dashboard(
    hass: HomeAssistant, url_path: str | None, config: dict[str, Any]
) -> None:
    dashboard = hass.data[LOVELACE_DATA].dashboards.get(url_path)
    if dashboard is None:
        raise HomeAssistantError(f"Dashboard {url_path} no longer exists")
    await dashboard.async_save(config)


def _yaml_files(config_dir: str) -> list[Path]:
    root = Path(config_dir)
    files = []
    for path in root.rglob("*.yaml"):
        relative = path.relative_to(root)
        if relative.parts[0] in _SKIP_DIRS:
            continue
        if len(relative.parts) == 1 and relative.name in _SKIP_FILES:
            continue
        files.append(path)
    return sorted(files)


def _read_yaml_files(config_dir: str) -> dict[str, str]:
    texts = {}
    for path in _yaml_files(config_dir):
        try:
            texts[str(path.relative_to(config_dir))] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as err:
            _LOGGER.debug("Cannot read %s: %s", path, err)
    return texts


async def async_yaml_reports(
    hass: HomeAssistant, id_map: dict[str, str]
) -> list[Report]:
    """YAML files (packages, includes, configuration.yaml) naming the old device."""
    texts = await hass.async_add_executor_job(_read_yaml_files, hass.config.config_dir)
    return [
        Report(name, "yaml_file")
        for name, text in texts.items()
        if any(old_id in text for old_id in id_map)
    ]


async def async_reference_corpus(hass: HomeAssistant) -> list[str]:
    """Every text that may name an entity ID, to check whether one is in use."""
    corpus = list(
        await hass.async_add_executor_job(_read_all_yaml, hass.config.config_dir)
    )
    corpus += [
        json.dumps(config, default=str) for _, config in await async_dashboards(hass)
    ]
    if "energy" in hass.config.components:
        from homeassistant.components.energy.data import async_get_manager

        manager = await async_get_manager(hass)
        corpus.append(json.dumps(manager.data or {}, default=str))
    for entry in hass.config_entries.async_entries():
        corpus.append(
            json.dumps({"data": entry.data, "options": entry.options}, default=str)
        )
    return corpus


def _read_all_yaml(config_dir: str) -> list[str]:
    texts = list(_read_yaml_files(config_dir).values())
    for name in ("automations.yaml", "scripts.yaml", "scenes.yaml"):
        path = Path(config_dir) / name
        if path.is_file():
            texts.append(path.read_text(encoding="utf-8"))
    return texts


def is_referenced(entity_id: str, corpus: list[str]) -> bool:
    """Whether the entity ID appears as a whole word in any of the texts."""
    pattern = re.compile(rf"(?<!\w){re.escape(entity_id)}(?!\w)")
    return any(pattern.search(text) for text in corpus)


def suggested_entity_id(entity_id: str, friendly_name: str | None) -> str | None:
    """The ID Home Assistant would give the entity today, if it differs."""
    if not friendly_name:
        return None
    domain = entity_id.split(".", 1)[0]
    suggestion = f"{domain}.{slugify(friendly_name)}"
    if suggestion == entity_id or suggestion == f"{domain}.":
        return None
    return suggestion


# Helpers that keep entity IDs in their settings, which can be updated safely.
HELPER_DOMAINS = {
    "bayesian",
    "compensation",
    "derivative",
    "filter",
    "generic_hygrostat",
    "generic_thermostat",
    "group",
    "history_stats",
    "integration",
    "min_max",
    "mold_indicator",
    "statistics",
    "switch_as_x",
    "template",
    "threshold",
    "tod",
    "trend",
    "utility_meter",
}


@dataclass
class SettingsPlan:
    """New settings for a helper (its config entry options) or the energy dashboard."""

    kind: str  # "helper" or "energy"
    key: str  # config entry ID, or "energy"
    label: str
    original: dict[str, Any]
    new: dict[str, Any]
    changes: list[Change] = field(default_factory=list)


def _mentions(text: str, entity_ids: list[str]) -> bool:
    return any(is_referenced(entity_id, [text]) for entity_id in entity_ids)


async def async_energy_prefs(hass: HomeAssistant) -> dict[str, Any] | None:
    if "energy" not in hass.config.components:
        return None
    from homeassistant.components.energy.data import async_get_manager

    manager = await async_get_manager(hass)
    return dict(manager.data) if manager.data else None


async def async_save_energy_prefs(hass: HomeAssistant, prefs: dict[str, Any]) -> None:
    from homeassistant.components.energy.data import async_get_manager

    manager = await async_get_manager(hass)
    await manager.async_update(
        {
            key: prefs[key]
            for key in (
                "energy_sources",
                "device_consumption",
                "device_consumption_water",
            )
            if key in prefs
        }
    )


async def async_plan_settings(
    hass: HomeAssistant, renames: dict[str, str]
) -> tuple[list[SettingsPlan], list[Report]]:
    """New settings for helpers and the energy dashboard that use renamed entities.

    Integrations other than helpers are reported: their settings are theirs.
    """
    plans: list[SettingsPlan] = []
    reports: list[Report] = []
    if not renames:
        return plans, reports
    olds = list(renames)
    for entry in hass.config_entries.async_entries():
        options_text = json.dumps(dict(entry.options), default=str)
        data_text = json.dumps(dict(entry.data), default=str)
        label = f"{entry.domain} '{entry.title}'"
        if entry.domain in HELPER_DOMAINS and _mentions(options_text, olds):
            original = json.loads(options_text)
            result = rewrite(original, {}, entity_renames=renames)
            plans.append(
                SettingsPlan(
                    "helper",
                    entry.entry_id,
                    label,
                    original,
                    result.config,
                    [
                        Change(f"{label}: {c.path}", c.old, c.new)
                        for c in result.changes
                    ],
                )
            )
        elif _mentions(options_text, olds) or _mentions(data_text, olds):
            reports.append(Report(label, "integration_settings"))
    prefs = await async_energy_prefs(hass)
    if prefs and _mentions(json.dumps(prefs, default=str), olds):
        original = json.loads(json.dumps(prefs, default=str))
        result = rewrite(original, {}, entity_renames=renames)
        plans.append(
            SettingsPlan(
                "energy",
                "energy",
                "energy dashboard",
                original,
                result.config,
                [
                    Change(f"energy dashboard: {c.path}", c.old, c.new)
                    for c in result.changes
                ],
            )
        )
    return plans, reports


async def async_apply_settings(hass: HomeAssistant, plan: SettingsPlan) -> None:
    """Write new helper options (reloading the helper) or energy settings."""
    if plan.kind == "energy":
        await async_save_energy_prefs(hass, plan.new)
        return
    entry = hass.config_entries.async_get_entry(plan.key)
    if entry is None:
        return
    hass.config_entries.async_update_entry(entry, options=plan.new)
    await hass.config_entries.async_reload(entry.entry_id)


async def async_current_settings(
    hass: HomeAssistant, kind: str, key: str
) -> dict[str, Any] | None:
    if kind == "energy":
        prefs = await async_energy_prefs(hass)
        return json.loads(json.dumps(prefs, default=str)) if prefs else None
    entry = hass.config_entries.async_get_entry(key)
    return json.loads(json.dumps(dict(entry.options), default=str)) if entry else None


async def async_entity_usage(
    hass: HomeAssistant, entity_ids: list[str]
) -> dict[str, tuple[list[str], list[str]]]:
    """Where each entity ID is used: (places Nine Lives can adjust, others)."""
    usage: dict[str, tuple[list[str], list[str]]] = {e: ([], []) for e in entity_ids}

    def note(text: str, where: str, editable: bool) -> None:
        for entity_id in entity_ids:
            if is_referenced(entity_id, [text]):
                usage[entity_id][0 if editable else 1].append(where)

    managed = await hass.async_add_executor_job(_read_managed, hass.config.config_dir)
    for name, text in managed.items():
        note(text, name, not _YAML_TAG_RE.search(text))
    others = await hass.async_add_executor_job(_read_yaml_files, hass.config.config_dir)
    for name, text in others.items():
        note(text, name, False)
    for dashboard, config in await async_dashboards(hass):
        title = _dashboard_title(dashboard.url_path, config)
        note(
            json.dumps(config, default=str),
            f"dashboard '{title}'",
            dashboard.mode == "storage",
        )
    for entry in hass.config_entries.async_entries():
        label = f"{entry.domain} '{entry.title}'"
        options_text = json.dumps(dict(entry.options), default=str)
        if entry.domain in HELPER_DOMAINS:
            note(options_text, label, True)
            note(json.dumps(dict(entry.data), default=str), label, False)
        else:
            note(options_text + json.dumps(dict(entry.data), default=str), label, False)
    prefs = await async_energy_prefs(hass)
    if prefs:
        note(json.dumps(prefs, default=str), "energy dashboard", True)
    return usage


_YAML_TAG_RE = re.compile(r"(?:^|[\s:\[,-])!\w")


def _read_managed(config_dir: str) -> dict[str, str]:
    texts = {}
    for name in ("automations.yaml", "scripts.yaml", "scenes.yaml"):
        path = Path(config_dir) / name
        if path.is_file():
            texts[name] = path.read_text(encoding="utf-8")
    return texts
