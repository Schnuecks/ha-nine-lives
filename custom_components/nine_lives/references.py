"""Find and rewrite device references in automation, script and scene configs.

Entity IDs need no rewriting: the new entities take over the old IDs. What does change
are the IDs that belong to the old device itself: its device ID and the registry IDs of
its entities, which device triggers, conditions and actions use.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Keys that mark a device trigger, condition or action.
_DEVICE_AUTOMATION_KEYS = {"device_id", "domain", "type"}


@dataclass(frozen=True)
class Change:
    """One rewritten value, with the path to it inside the config."""

    path: str
    old: str
    new: str


@dataclass(frozen=True)
class Review:
    """A device automation that may not exist on the new device."""

    path: str
    reason: str


@dataclass
class RewriteResult:
    config: Any
    changes: list[Change]
    reviews: list[Review]


def rewrite(
    config: Any,
    id_map: dict[str, str],
    entity_domains: dict[str, str] | None = None,
    new_integrations: set[str] | None = None,
) -> RewriteResult:
    """Return a copy of config with every ID in id_map replaced.

    id_map maps the old device ID and the old entity registry IDs to the new ones.
    entity_domains maps new entity registry IDs to their domain; device automations
    bound to an entity of the same domain are expected to work on the new device,
    and so are those of new_integrations (the integrations of the new device); all
    others are reported for review.
    """
    entity_domains = entity_domains or {}
    new_integrations = new_integrations or set()
    changes: list[Change] = []
    reviews: list[Review] = []

    def walk(node: Any, path: str) -> Any:
        if isinstance(node, str):
            if node in id_map:
                changes.append(Change(path, node, id_map[node]))
                return id_map[node]
            return node
        if isinstance(node, list):
            return [walk(item, f"{path}[{i}]") for i, item in enumerate(node)]
        if isinstance(node, dict):
            result = {k: walk(v, f"{path}.{k}" if path else k) for k, v in node.items()}
            if node.keys() >= _DEVICE_AUTOMATION_KEYS and node["device_id"] in id_map:
                domain = node["domain"]
                entity = result.get("entity_id")
                if (
                    domain not in new_integrations
                    and entity_domains.get(entity) != domain
                ):
                    if "condition" in node:
                        kind = "condition"
                    elif "trigger" in node or "platform" in node:
                        kind = "trigger"
                    else:
                        kind = "action"
                    reviews.append(
                        Review(path, f"device {kind} '{node['type']}' of {domain}")
                    )
            return result
        return node

    return RewriteResult(walk(config, ""), changes, reviews)
