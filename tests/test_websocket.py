"""Tests for the WebSocket commands."""

from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nine_lives.const import DOMAIN


@pytest.fixture
def expected_lingering_timers() -> bool:
    """A swap hides the recorder's expected messages for a while, using a timer."""
    return True


@pytest.fixture
async def devices(hass: HomeAssistant, tmp_path: Path):
    hass.config.config_dir = str(tmp_path)
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)

    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    result = {}
    for name in ("old", "new"):
        cfg = MockConfigEntry(domain=f"{name}_integration")
        cfg.add_to_hass(hass)
        device = dev_reg.async_get_or_create(
            config_entry_id=cfg.entry_id, identifiers={(cfg.domain, name)}
        )
        for kind, unit in (("temperature", "°C"), ("humidity", "%")):
            ent_reg.async_get_or_create(
                "sensor",
                cfg.domain,
                f"{name}-{kind}",
                device_id=device.id,
                original_device_class=kind,
                unit_of_measurement=unit,
                suggested_object_id=f"{name}_{kind}",
            )
        result[name] = device.id
    return result


async def test_propose_preview_apply_undo(
    hass: HomeAssistant, hass_ws_client, devices
) -> None:
    client = await hass_ws_client(hass)
    ids = {"old_device_id": devices["old"], "new_device_id": devices["new"]}

    await client.send_json_auto_id({"type": "nine_lives/propose", **ids})
    proposal = (await client.receive_json())["result"]
    assert proposal["pairs"] == [
        {"old": "sensor.old_temperature", "new": "sensor.new_temperature"},
        {"old": "sensor.old_humidity", "new": "sensor.new_humidity"},
    ]

    request = {**ids, "pairs": proposal["pairs"]}
    await client.send_json_auto_id({"type": "nine_lives/preview", **request})
    preview = await client.receive_json()
    assert preview["success"]
    assert preview["result"]["files"] == []

    await client.send_json_auto_id({"type": "nine_lives/apply", **request})
    backup_id = (await client.receive_json())["result"]["backup_id"]
    ent_reg = er.async_get(hass)
    assert ent_reg.async_get("sensor.old_temperature").unique_id == "new-temperature"

    await client.send_json_auto_id({"type": "nine_lives/pending"})
    assert (await client.receive_json())["result"] == []

    await client.send_json_auto_id({"type": "nine_lives/backups"})
    backups = (await client.receive_json())["result"]
    assert [b["backup_id"] for b in backups] == [backup_id]

    await client.send_json_auto_id({"type": "nine_lives/undo", "backup_id": backup_id})
    assert (await client.receive_json())["result"] == {"notes": []}

    await client.send_json_auto_id({"type": "nine_lives/backups"})
    history = (await client.receive_json())["result"]
    assert [(h["backup_id"], h["can_undo"]) for h in history] == [(backup_id, False)]
    assert history[0]["undone"]
    assert ent_reg.async_get("sensor.new_temperature").unique_id == "new-temperature"


async def test_errors_are_reported(hass: HomeAssistant, hass_ws_client, devices):
    client = await hass_ws_client(hass)

    await client.send_json_auto_id(
        {
            "type": "nine_lives/preview",
            "old_device_id": devices["old"],
            "new_device_id": devices["old"],
            "pairs": [],
        }
    )
    response = await client.receive_json()
    assert not response["success"]
    assert response["error"]["message"] == "Old and new device are the same"


async def test_commands_need_an_admin(
    hass: HomeAssistant, hass_ws_client, hass_read_only_access_token, devices
) -> None:
    client = await hass_ws_client(hass, hass_read_only_access_token)

    await client.send_json_auto_id({"type": "nine_lives/backups"})
    response = await client.receive_json()
    assert response["error"]["code"] == "unauthorized"


async def test_devices_tell_old_and_new_apart(
    hass: HomeAssistant, hass_ws_client, devices
) -> None:
    ent_reg = er.async_get(hass)
    identify = ent_reg.async_get_or_create(
        "button",
        "new_integration",
        "new-identify",
        device_id=devices["new"],
        original_device_class="identify",
    )
    hass.states.async_set("sensor.new_temperature", "21.5")
    client = await hass_ws_client(hass)

    await client.send_json_auto_id({"type": "nine_lives/devices"})
    result = {d["id"]: d for d in (await client.receive_json())["result"]}

    old, new = result[devices["old"]], result[devices["new"]]
    assert old["created_at"] <= new["created_at"]
    assert old["available"] is False
    assert new["available"] is True
    assert old["identify"] is None
    assert new["identify"] == identify.entity_id
    assert new["integration"] == "new_integration"


async def test_no_deprecated_registry_access(
    hass: HomeAssistant, hass_ws_client, devices, caplog
) -> None:
    """Home Assistant warns about deprecated registry APIs; Nine Lives uses none."""
    client = await hass_ws_client(hass)

    await client.send_json_auto_id({"type": "nine_lives/devices"})
    assert (await client.receive_json())["success"]
    await client.send_json_auto_id({"type": "nine_lives/removed_devices"})
    removed = (await client.receive_json())["result"]

    assert removed == {"supported": True, "devices": []}
    assert "deprecated" not in caplog.text
