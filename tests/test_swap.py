"""Tests for applying and undoing a swap."""

import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components import persistent_notification
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nine_lives.swap import (
    SwapError,
    SwapManager,
    async_plan,
    async_suggest_ids,
)

OLD_TEMP = "sensor.bathroom_temperature"
OLD_BATTERY = "sensor.bathroom_battery"


@pytest.fixture
def expected_lingering_timers() -> bool:
    """A swap hides the recorder's expected messages for a while, using a timer."""
    return True


@pytest.fixture
def setup(hass: HomeAssistant, tmp_path: Path):
    """An Aqara sensor on ZHA, its IKEA successor on Matter and one automation."""
    hass.config.config_dir = str(tmp_path)
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    zha = MockConfigEntry(domain="zha")
    matter = MockConfigEntry(domain="matter")
    zha.add_to_hass(hass)
    matter.add_to_hass(hass)

    old_dev = dev_reg.async_get_or_create(
        config_entry_id=zha.entry_id, identifiers={("zha", "aqara")}, name="Aqara"
    )
    new_dev = dev_reg.async_get_or_create(
        config_entry_id=matter.entry_id, identifiers={("matter", "ikea")}, name="IKEA"
    )
    dev_reg.async_update_device(old_dev.id, area_id="bathroom", labels={"climate"})

    def entity(cfg, dev, unique_id, object_id):
        entry = ent_reg.async_get_or_create(
            "sensor",
            cfg.domain,
            unique_id,
            config_entry=cfg,
            device_id=dev.id,
            suggested_object_id=object_id,
        )
        hass.states.async_set(entry.entity_id, "1")
        return entry

    old_temp = entity(zha, old_dev, "aqara-temp", "bathroom_temperature")
    entity(zha, old_dev, "aqara-battery", "bathroom_battery")
    new_temp = entity(matter, new_dev, "ikea-temp", "ikea_temperature")
    new_battery = entity(matter, new_dev, "ikea-battery", "ikea_battery")
    ent_reg.async_update_entity(OLD_TEMP, name="Bad", icon="mdi:shower")

    automations = tmp_path / "automations.yaml"
    automations.write_text(
        f"""- id: '1'
  alias: Bathroom too warm
  triggers:
  - trigger: device
    device_id: {old_dev.id}
    entity_id: {old_temp.id}
    domain: sensor
    type: temperature
    above: 25
  - trigger: device
    device_id: {old_dev.id}
    domain: zha
    type: device_offline
  actions:
  - action: notify.phone
    data:
      message: '{{{{ states("{OLD_TEMP}") }}}}'
""",
        encoding="utf-8",
    )
    return {
        "old_dev": old_dev,
        "new_dev": new_dev,
        "old_temp": old_temp,
        "new_temp": new_temp,
        "new_battery": new_battery,
        "pairs": [
            (OLD_TEMP, new_temp.entity_id),
            (OLD_BATTERY, new_battery.entity_id),
        ],
        "automations": automations,
    }


async def test_plan_lists_changes_and_reviews(hass: HomeAssistant, setup) -> None:
    plan = await async_plan(
        hass, setup["old_dev"].id, setup["new_dev"].id, setup["pairs"]
    )

    automation = plan.files[0]
    assert automation.kind == "automation"
    assert [c.path for c in automation.changes] == [
        "automation 'Bathroom too warm': triggers[0].device_id",
        "automation 'Bathroom too warm': triggers[0].entity_id",
        "automation 'Bathroom too warm': triggers[1].device_id",
    ]
    assert [r.reason for r in automation.reviews] == [
        "device trigger 'device_offline' of zha"
    ]
    # Planning changes nothing.
    assert setup["old_dev"].id in setup["automations"].read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("pairs", "message"),
    [
        ([], "No entities"),
        ([(OLD_TEMP, OLD_BATTERY)], "does not belong to the new device"),
        ([(OLD_TEMP, "sensor.ikea_temperature")] * 2, "only be used once"),
    ],
)
async def test_plan_rejects_invalid_requests(
    hass: HomeAssistant, setup, pairs, message
) -> None:
    with pytest.raises(SwapError, match=message):
        await async_plan(hass, setup["old_dev"].id, setup["new_dev"].id, pairs)


async def test_apply_hands_over_ids_settings_and_references(
    hass: HomeAssistant, setup
) -> None:
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    manager = SwapManager(hass)
    plan = await async_plan(
        hass, setup["old_dev"].id, setup["new_dev"].id, setup["pairs"]
    )

    await manager.async_apply(plan)

    taken_over = ent_reg.async_get(OLD_TEMP)
    assert taken_over.unique_id == "ikea-temp"
    assert taken_over.id == setup["new_temp"].id
    assert (taken_over.name, taken_over.icon) == ("Bad", "mdi:shower")
    assert ent_reg.async_get("sensor.ikea_temperature") is None
    assert ent_reg.async_get(OLD_BATTERY).unique_id == "ikea-battery"

    new_dev = dev_reg.async_get(setup["new_dev"].id)
    assert (new_dev.area_id, new_dev.labels) == ("bathroom", {"climate"})
    old_dev = dev_reg.async_get(setup["old_dev"].id)
    assert old_dev.disabled_by is dr.DeviceEntryDisabler.USER

    text = setup["automations"].read_text(encoding="utf-8")
    assert setup["old_dev"].id not in text
    assert setup["old_temp"].id not in text
    assert setup["new_temp"].id in text
    assert f'states("{OLD_TEMP}")' in text


async def test_old_entity_comes_back_with_its_registry_id(
    hass: HomeAssistant, setup
) -> None:
    """Undo relies on Home Assistant restoring removed entries by unique ID."""
    ent_reg = er.async_get(hass)
    manager = SwapManager(hass)
    plan = await async_plan(
        hass, setup["old_dev"].id, setup["new_dev"].id, setup["pairs"]
    )
    backup_id = await manager.async_apply(plan)

    with patch.object(
        hass.config_entries, "async_reload", AsyncMock(return_value=True)
    ) as reload:
        notes = await manager.async_undo(backup_id)

    assert notes == []
    reload.assert_awaited_once()
    assert ent_reg.async_get("sensor.ikea_temperature").unique_id == "ikea-temp"
    assert ent_reg.async_get("sensor.ikea_temperature").name is None
    assert ent_reg.async_get(OLD_TEMP) is None

    # What the integration does on reload: create the entity again.
    restored = ent_reg.async_get_or_create(
        "sensor", "zha", "aqara-temp", config_entry=None
    )
    assert restored.entity_id == OLD_TEMP
    assert restored.id == setup["old_temp"].id
    assert restored.name == "Bad"

    assert dr.async_get(hass).async_get(setup["old_dev"].id).disabled_by is None
    assert setup["old_temp"].id in setup["automations"].read_text(encoding="utf-8")
    assert manager.backups == {}


async def test_undo_keeps_edits_made_after_the_swap(hass: HomeAssistant, setup) -> None:
    manager = SwapManager(hass)
    plan = await async_plan(
        hass, setup["old_dev"].id, setup["new_dev"].id, setup["pairs"]
    )
    backup_id = await manager.async_apply(plan)
    automations = setup["automations"]
    automations.write_text(
        automations.read_text(encoding="utf-8").replace("above: 25", "above: 27"),
        encoding="utf-8",
    )

    with patch.object(hass.config_entries, "async_reload", AsyncMock()):
        await manager.async_undo(backup_id)

    text = automations.read_text(encoding="utf-8")
    assert "above: 27" in text
    assert setup["old_dev"].id in text
    assert setup["new_dev"].id not in text


async def test_files_with_yaml_tags_are_not_touched(hass: HomeAssistant, setup) -> None:
    automations = setup["automations"]
    original = automations.read_text(encoding="utf-8") + "  mode: !secret mode\n"
    automations.write_text(original, encoding="utf-8")

    plan = await async_plan(
        hass, setup["old_dev"].id, setup["new_dev"].id, setup["pairs"]
    )
    await SwapManager(hass).async_apply(plan)

    assert plan.files[0].blocked == "yaml_tags"
    assert automations.read_text(encoding="utf-8") == original


async def test_backups_survive_a_restart(hass: HomeAssistant, setup) -> None:
    manager = SwapManager(hass)
    plan = await async_plan(
        hass, setup["old_dev"].id, setup["new_dev"].id, setup["pairs"]
    )
    backup_id = await manager.async_apply(plan)

    reloaded = SwapManager(hass)
    await reloaded.async_load()

    assert list(reloaded.backups) == [backup_id]


async def test_expected_recorder_messages_are_hidden(
    hass: HomeAssistant, setup, caplog
) -> None:
    plan = await async_plan(
        hass, setup["old_dev"].id, setup["new_dev"].id, setup["pairs"]
    )
    await SwapManager(hass).async_apply(plan)
    logger = logging.getLogger("homeassistant.components.recorder.entity_registry")

    logger.warning("Cannot migrate %s to %s", "sensor.ikea_temperature", OLD_TEMP)
    logger.warning("Cannot migrate %s to %s", "sensor.other", OLD_TEMP)

    assert "Cannot migrate sensor.ikea_temperature" not in caplog.text
    assert "sensor.other" in caplog.text


async def test_dashboards_are_rewritten_and_restored(
    hass: HomeAssistant, setup
) -> None:
    await async_setup_component(hass, "lovelace", {})
    dashboard = hass.data[LOVELACE_DATA].dashboards[None]
    original = {
        "views": [
            {"cards": [{"type": "tile", "entity": OLD_TEMP}]},
            {
                "cards": [
                    {"type": "custom:device-card", "device_id": setup["old_dev"].id}
                ]
            },
        ]
    }
    await dashboard.async_save(original)
    manager = SwapManager(hass)

    plan = await async_plan(
        hass, setup["old_dev"].id, setup["new_dev"].id, setup["pairs"]
    )
    assert [c.path for c in plan.dashboards[0].changes] == [
        "dashboard 'Overview': views[1].cards[0].device_id"
    ]
    backup_id = await manager.async_apply(plan)

    saved = await dashboard.async_load(False)
    assert saved["views"][1]["cards"][0]["device_id"] == setup["new_dev"].id
    assert saved["views"][0]["cards"][0]["entity"] == OLD_TEMP

    with patch.object(hass.config_entries, "async_reload", AsyncMock()):
        await manager.async_undo(backup_id)
    assert await dashboard.async_load(False) == original


async def test_yaml_files_are_reported_not_changed(
    hass: HomeAssistant, setup, tmp_path: Path
) -> None:
    package = tmp_path / "packages" / "bathroom.yaml"
    package.parent.mkdir()
    text = f"homeassistant:\n  customize: {{}}\n# device {setup['old_dev'].id}\n"
    package.write_text(text, encoding="utf-8")

    plan = await async_plan(
        hass, setup["old_dev"].id, setup["new_dev"].id, setup["pairs"]
    )
    await SwapManager(hass).async_apply(plan)

    assert [(r.where, r.reason) for r in plan.reports] == [
        ("packages/bathroom.yaml", "yaml_file")
    ]
    assert package.read_text(encoding="utf-8") == text


async def test_unused_old_ids_can_get_a_tidier_id(hass: HomeAssistant, setup) -> None:
    ent_reg = er.async_get(hass)
    hass.states.async_set(OLD_BATTERY, "90", {"friendly_name": "Bad Batterie"})
    # The temperature is used in the automation's template, so its ID must stay.
    hass.states.async_set(OLD_TEMP, "21", {"friendly_name": "Bad Temperatur"})

    suggestions = await async_suggest_ids(hass, [OLD_TEMP, OLD_BATTERY])
    assert suggestions == {OLD_BATTERY: "sensor.bad_batterie"}

    with pytest.raises(SwapError, match="in use"):
        await async_plan(
            hass,
            setup["old_dev"].id,
            setup["new_dev"].id,
            setup["pairs"],
            {OLD_TEMP: "sensor.bad_temperatur"},
        )

    manager = SwapManager(hass)
    plan = await async_plan(
        hass, setup["old_dev"].id, setup["new_dev"].id, setup["pairs"], suggestions
    )
    backup_id = await manager.async_apply(plan)

    assert ent_reg.async_get("sensor.bad_batterie").unique_id == "ikea-battery"
    assert ent_reg.async_get(OLD_BATTERY) is None
    assert ent_reg.async_get(OLD_TEMP).unique_id == "ikea-temp"

    with patch.object(hass.config_entries, "async_reload", AsyncMock()):
        await manager.async_undo(backup_id)
    assert ent_reg.async_get("sensor.ikea_battery").unique_id == "ikea-battery"
    assert ent_reg.async_get("sensor.bad_batterie") is None
    restored = ent_reg.async_get_or_create("sensor", "zha", "aqara-battery")
    assert restored.entity_id == OLD_BATTERY


async def test_swap_notifies_and_undo_dismisses(hass: HomeAssistant, setup) -> None:
    await async_setup_component(hass, "persistent_notification", {})
    hass.config.language = "de"
    manager = SwapManager(hass)
    plan = await async_plan(
        hass, setup["old_dev"].id, setup["new_dev"].id, setup["pairs"]
    )

    backup_id = await manager.async_apply(plan)

    notification = _notifications(hass)[f"nine_lives_{backup_id}"]
    assert notification["title"] == "Nine Lives: Aqara ersetzt"
    assert "**IKEA** führt **Aqara** fort: 2 Entitäten" in notification["message"]

    with patch.object(hass.config_entries, "async_reload", AsyncMock()):
        await manager.async_undo(backup_id)
    assert f"nine_lives_{backup_id}" not in _notifications(hass)


def _notifications(hass: HomeAssistant) -> dict:
    return persistent_notification._async_get_or_create_notifications(hass)


async def test_history_keeps_what_a_swap_did(hass: HomeAssistant, setup) -> None:
    manager = SwapManager(hass)
    plan = await async_plan(
        hass, setup["old_dev"].id, setup["new_dev"].id, setup["pairs"]
    )
    swap_id = await manager.async_apply(plan)

    entry = manager.history[swap_id]
    assert (entry["old_device"], entry["new_device"]) == ("Aqara", "IKEA")
    assert entry["pairs"][0] == {
        "old": OLD_TEMP,
        "new": "sensor.ikea_temperature",
        "final": OLD_TEMP,
    }
    assert "automation 'Bathroom too warm': triggers[0].device_id" in entry["changes"]
    assert [r["reason"] for r in entry["reviews"]] == [
        "device trigger 'device_offline' of zha"
    ]

    with patch.object(hass.config_entries, "async_reload", AsyncMock()):
        await manager.async_undo(swap_id)

    # The backup is gone, the history stays with the time of the undo.
    assert swap_id not in manager.backups
    assert manager.history[swap_id]["undone"] is not None
    reloaded = SwapManager(hass)
    await reloaded.async_load()
    assert reloaded.history[swap_id]["undone"] == manager.history[swap_id]["undone"]


async def test_old_backups_get_a_history_entry(hass: HomeAssistant, setup) -> None:
    manager = SwapManager(hass)
    plan = await async_plan(
        hass, setup["old_dev"].id, setup["new_dev"].id, setup["pairs"]
    )
    swap_id = await manager.async_apply(plan)
    # A swap from before the history existed: only the backup is stored.
    manager.history.clear()
    await manager._async_save()

    reloaded = SwapManager(hass)
    await reloaded.async_load()

    entry = reloaded.history[swap_id]
    assert [p["final"] for p in entry["pairs"]] == [OLD_TEMP, OLD_BATTERY]
    assert entry["changes"] == []
