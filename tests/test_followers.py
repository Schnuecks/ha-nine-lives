"""Tests for moving a Battery Notes note along with a swap."""

import json
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nine_lives import followers
from custom_components.nine_lives.swap import SwapManager, async_plan

from .test_swap import OLD_BATTERY, OLD_TEMP, expected_lingering_timers, setup  # noqa: F401

LIBRARY = {
    "devices": [
        {
            "manufacturer": "IKEA of Sweden",
            "model": "TIMMERFLOTTE",
            "battery_type": "CR2032",
        },
        {
            "manufacturer": "IKEA of Sweden",
            "model": "TIMMERFLOTTE",
            "model_id": "32773",
            "hw_version": "P2.1",
            "battery_type": "AAA",
            "battery_quantity": 2,
        },
    ]
}


def _note(device_id: str, title: str, battery: str = "CR2032") -> ConfigSubentryData:
    return ConfigSubentryData(
        data=MappingProxyType(
            {"device_id": device_id, "battery_type": battery, "battery_quantity": 1}
        ),
        subentry_type="battery_note",
        title=title,
        unique_id=f"bn_{device_id}",
    )


@pytest.fixture
def notes(hass: HomeAssistant, setup, tmp_path: Path):  # noqa: F811
    """Battery Notes with a note for the old device, its entities and its library."""
    dev_reg = dr.async_get(hass)
    dev_reg.async_update_device(
        setup["new_dev"].id,
        manufacturer="IKEA of Sweden",
        model="TIMMERFLOTTE",
        model_id="32773",
        hw_version="P2.1",
    )
    library = tmp_path / ".storage" / "battery_notes" / "library.json"
    library.parent.mkdir(parents=True)
    library.write_text(json.dumps(LIBRARY), encoding="utf-8")
    entry = MockConfigEntry(
        domain="battery_notes",
        version=5,
        subentries_data=[_note(setup["old_dev"].id, "Aqara")],
    )
    entry.add_to_hass(hass)
    sub = next(iter(entry.subentries.values()))
    ent_reg = er.async_get(hass)
    ids = {}
    for suffix in ("_battery_plus", "_battery_last_replaced"):
        e = ent_reg.async_get_or_create(
            "sensor",
            "battery_notes",
            f"bn_{setup['old_dev'].id}{suffix}",
            config_entry=entry,
            config_subentry_id=sub.subentry_id,
            device_id=setup["old_dev"].id,
            suggested_object_id=f"bathroom{suffix}",
        )
        ids[suffix] = e.entity_id
    hass.states.async_set(ids["_battery_last_replaced"], "2024-10-22T06:42:16+00:00")
    calls: list[ServiceCall] = []

    async def _set_replaced(call: ServiceCall) -> None:
        calls.append(call)

    hass.services.async_register("battery_notes", "set_battery_replaced", _set_replaced)
    return {"entry": entry, "sub": sub, "ids": ids, "calls": calls}


async def test_library_prefers_the_most_specific_entry() -> None:
    dev = SimpleNamespace(
        manufacturer="ikea of sweden",
        model="TIMMERFLOTTE",
        model_id="32773",
        hw_version="P2.1",
    )
    assert followers.battery_from_library(LIBRARY["devices"], dev) == ("AAA", 2)
    other = SimpleNamespace(
        manufacturer="IKEA of Sweden",
        model="TIMMERFLOTTE",
        model_id=None,
        hw_version=None,
    )
    assert followers.battery_from_library(LIBRARY["devices"], other) == ("CR2032", 1)
    assert (
        followers.battery_from_library(
            LIBRARY["devices"],
            SimpleNamespace(
                manufacturer=None, model="x", model_id=None, hw_version=None
            ),
        )
        is None
    )


async def test_the_note_moves_with_the_swap_and_back(
    hass: HomeAssistant,
    setup,  # noqa: F811
    notes,
) -> None:
    ent_reg = er.async_get(hass)
    old_id, new_id = setup["old_dev"].id, setup["new_dev"].id
    # A note of the new device that came in through discovery is replaced.
    hass.config_entries.async_add_subentry(
        notes["entry"], followers.ConfigSubentry(**_note(new_id, "IKEA", "AAA"))
    )
    manager = SwapManager(hass)
    plan = await async_plan(hass, old_id, new_id, setup["pairs"])
    swap_id = await manager.async_apply(plan)

    entry = hass.config_entries.async_get_entry(notes["entry"].entry_id)
    assert list(entry.subentries) == [notes["sub"].subentry_id]
    sub = entry.subentries[notes["sub"].subentry_id]
    assert sub.data["device_id"] == new_id
    assert (sub.data["battery_type"], sub.data["battery_quantity"]) == ("AAA", 2)
    assert (sub.unique_id, sub.title) == (f"bn_{new_id}", "IKEA")
    plus = ent_reg.async_get(notes["ids"]["_battery_plus"])
    assert plus.unique_id == f"bn_{new_id}_battery_plus"
    assert plus.device_id == new_id
    # Disabling the old device must not leave the moved note disabled.
    assert plus.disabled_by is None
    # The date the battery was last replaced stays.
    assert notes["calls"][0].data == {
        "device_id": new_id,
        "datetime_replaced": "2024-10-22T06:42:16+00:00",
    }

    await manager.async_undo(swap_id)

    entry = hass.config_entries.async_get_entry(notes["entry"].entry_id)
    sub = entry.subentries[notes["sub"].subentry_id]
    assert sub.data["device_id"] == old_id
    assert sub.data["battery_type"] == "CR2032"
    assert sub.unique_id == f"bn_{old_id}"
    plus = ent_reg.async_get(notes["ids"]["_battery_plus"])
    assert (plus.unique_id, plus.device_id) == (f"bn_{old_id}_battery_plus", old_id)
    assert sorted(s.title for s in entry.subentries.values()) == ["Aqara", "IKEA"]


async def test_note_entities_are_not_paired(
    hass: HomeAssistant,
    setup,  # noqa: F811
    notes,
) -> None:
    from custom_components.nine_lives.websocket import _entity_infos

    ids = [i.entity_id for i in _entity_infos(hass, setup["old_dev"].id)]
    assert OLD_TEMP in ids and OLD_BATTERY in ids
    assert not set(ids) & set(notes["ids"].values())


async def test_swap_without_battery_notes(hass: HomeAssistant, setup) -> None:  # noqa: F811
    manager = SwapManager(hass)
    plan = await async_plan(
        hass, setup["old_dev"].id, setup["new_dev"].id, setup["pairs"]
    )
    swap_id = await manager.async_apply(plan)
    assert "followers" not in manager.backups[swap_id]


async def test_preview_shows_what_moves_and_what_stays(
    hass: HomeAssistant,
    setup,  # noqa: F811
    notes,
) -> None:
    other = MockConfigEntry(domain="powercalc")
    other.add_to_hass(hass)
    er.async_get(hass).async_get_or_create(
        "sensor",
        "powercalc",
        "aqara-power",
        config_entry=other,
        device_id=setup["old_dev"].id,
        suggested_object_id="bathroom_power",
    )
    plan = await async_plan(
        hass, setup["old_dev"].id, setup["new_dev"].id, setup["pairs"]
    )
    moves, stays = plan.as_dict()["attached"]
    assert moves["integration"] == "battery_notes" and moves["moves"]
    assert moves["battery"] == "2× AAA"
    assert sorted(moves["entities"]) == sorted(notes["ids"].values())
    assert stays == {
        "integration": "powercalc",
        "moves": False,
        "entities": ["sensor.bathroom_power"],
    }
