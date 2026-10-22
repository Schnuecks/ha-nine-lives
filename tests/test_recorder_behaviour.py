"""How the recorder treats entity ID changes.

These tests pin down Home Assistant behaviour that MeshMove's swap strategy relies on.
If a Home Assistant update changes it, they fail before users lose history.
"""

from datetime import timedelta

import pytest
from homeassistant.components.recorder import Recorder, get_instance, history
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

OLD = "sensor.bathroom_temperature"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations():
    """The recorder must start before hass, so skip the custom integration fixture."""
    return


async def _history(hass: HomeAssistant, entity_id: str) -> list[str]:
    start = dt_util.utcnow() - timedelta(hours=1)

    def _get():
        states = history.state_changes_during_period(hass, start, entity_id=entity_id)
        return [s.state for s in states.get(entity_id, [])]

    return await get_instance(hass).async_add_executor_job(_get)


async def _setup_pair(hass: HomeAssistant) -> tuple[er.EntityRegistry, str]:
    reg = er.async_get(hass)
    reg.async_get_or_create(
        "sensor", "zha", "old-device", suggested_object_id="bathroom_temperature"
    )
    new = reg.async_get_or_create(
        "sensor", "matter", "new-device", suggested_object_id="ikea_temperature"
    ).entity_id
    hass.states.async_set(OLD, "21.0")
    hass.states.async_set(new, "22.0")
    await async_wait_recording_done(hass)
    return reg, new


async def test_rename_moves_history_with_the_entity(
    recorder_mock: Recorder, hass: HomeAssistant
) -> None:
    """Renaming old -> *_old and new -> old splits the history: no continuity."""
    reg, new = await _setup_pair(hass)

    # The state machine blocks IDs that still have a state, like a running entity does.
    hass.states.async_remove(OLD)
    reg.async_update_entity(OLD, new_entity_id=f"{OLD}_old")
    await async_wait_recording_done(hass)
    hass.states.async_remove(new)
    reg.async_update_entity(new, new_entity_id=OLD)
    hass.states.async_set(OLD, "22.5")
    await async_wait_recording_done(hass)

    assert "21.0" in await _history(hass, f"{OLD}_old")
    assert "21.0" not in await _history(hass, OLD)
    assert (await _history(hass, OLD))[-1:] == ["22.5"]


async def test_removed_entity_leaves_history_for_the_successor(
    recorder_mock: Recorder, hass: HomeAssistant
) -> None:
    """Removing the old entry first keeps its history under the ID, and the new
    entity continues it once it takes that ID (the recorder refuses to move the new
    entity's own short history onto an ID that is in use)."""
    reg, new = await _setup_pair(hass)

    reg.async_remove(OLD)
    hass.states.async_remove(OLD)
    await async_wait_recording_done(hass)
    hass.states.async_remove(new)
    reg.async_update_entity(new, new_entity_id=OLD)
    hass.states.async_set(OLD, "22.5")
    await async_wait_recording_done(hass)

    # The empty entry is the gap while no entity owned the ID.
    assert await _history(hass, OLD) == ["21.0", "", "22.5"]
