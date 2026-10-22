"""Pair the entities of the old device with those of the new one."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EntityInfo:
    """What Nine Lives needs to know about one entity."""

    entity_id: str
    registry_id: str
    device_class: str | None = None
    unit: str | None = None
    state_class: str | None = None
    name: str | None = None

    @property
    def domain(self) -> str:
        return self.entity_id.split(".", 1)[0]


@dataclass
class Pairing:
    """Proposed pairs plus the entities that found no partner."""

    pairs: list[tuple[EntityInfo, EntityInfo]] = field(default_factory=list)
    unmatched_old: list[EntityInfo] = field(default_factory=list)
    unmatched_new: list[EntityInfo] = field(default_factory=list)


def _score(old: EntityInfo, new: EntityInfo) -> int:
    """How well two entities fit; 0 means they must not be paired."""
    if old.domain != new.domain:
        return 0
    if old.device_class != new.device_class:
        # A temperature sensor never replaces a humidity sensor. If only one side has
        # a device class, the unit has to confirm the match (LQI is not illuminance).
        if old.device_class and new.device_class:
            return 0
        if old.unit is None or old.unit != new.unit:
            return 0
    score = 1
    if old.device_class and old.device_class == new.device_class:
        score += 4
    if old.unit == new.unit:
        score += 2
    if old.state_class == new.state_class:
        score += 1
    if old.name and new.name and old.name.casefold() == new.name.casefold():
        score += 1
    return score


def propose_pairs(old: list[EntityInfo], new: list[EntityInfo]) -> Pairing:
    """Pair every old entity with the best fitting new one, best fits first."""
    candidates = sorted(
        (
            (score, i, j)
            for i, o in enumerate(old)
            for j, n in enumerate(new)
            if (score := _score(o, n))
        ),
        key=lambda c: (-c[0], c[1], c[2]),
    )
    used_old: set[int] = set()
    used_new: set[int] = set()
    result = Pairing()
    for _score_value, i, j in candidates:
        if i in used_old or j in used_new:
            continue
        used_old.add(i)
        used_new.add(j)
        result.pairs.append((old[i], new[j]))
    result.pairs.sort(key=lambda p: old.index(p[0]))
    result.unmatched_old = [o for i, o in enumerate(old) if i not in used_old]
    result.unmatched_new = [n for j, n in enumerate(new) if j not in used_new]
    return result
