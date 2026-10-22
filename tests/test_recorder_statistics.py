"""How long-term statistics behave when a successor takes over a meter's entity ID.

Energy meters keep a running sum. When a new meter starting at 0 continues the old
meter's statistics, the drop must count as a meter reset, not as negative consumption.
"""

from datetime import datetime, timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.recorder import Recorder, get_instance
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
    do_adhoc_statistics,
    statistics_during_period,
)

from custom_components.nine_lives.energy import async_try_apply
from custom_components.nine_lives.swap import SwapManager, async_plan

OLD = "sensor.washer_energy"
ATTRS = {
    "device_class": "energy",
    "state_class": "total_increasing",
    "unit_of_measurement": "kWh",
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations():
    """The recorder must start before hass, so skip the custom integration fixture."""
    return


async def _compile(hass: HomeAssistant, start: datetime) -> None:
    do_adhoc_statistics(hass, start=start)
    await async_wait_recording_done(hass)


async def _sums(hass: HomeAssistant, start: datetime) -> list[float]:
    stats = await get_instance(hass).async_add_executor_job(
        statistics_during_period, hass, start, None, {OLD}, "5minute"
    )
    return [row["sum"] for row in stats.get(OLD, [])]


async def test_new_meter_continues_sum_of_removed_meter(
    recorder_mock: Recorder, hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    await async_setup_component(hass, "sensor", {})
    reg = er.async_get(hass)
    reg.async_get_or_create(
        "sensor", "zha", "old-plug", suggested_object_id="washer_energy"
    )
    new = reg.async_get_or_create(
        "sensor", "matter", "new-plug", suggested_object_id="new_plug_energy"
    ).entity_id

    p0 = dt_util.utcnow().replace(minute=0, second=0, microsecond=0) + timedelta(
        hours=1
    )
    period = timedelta(minutes=5)

    # Old meter: 100 -> 110 kWh in the first period, 115 in the second.
    freezer.move_to(p0 + timedelta(minutes=1))
    hass.states.async_set(OLD, "100", ATTRS)
    freezer.move_to(p0 + timedelta(minutes=3))
    hass.states.async_set(OLD, "110", ATTRS)
    freezer.move_to(p0 + period + timedelta(minutes=1))
    hass.states.async_set(OLD, "115", ATTRS)
    await async_wait_recording_done(hass)
    await _compile(hass, p0)
    await _compile(hass, p0 + period)

    # Swap in the third period: old entry removed, new meter (at 0) takes the ID.
    freezer.move_to(p0 + 2 * period + timedelta(minutes=1))
    reg.async_remove(OLD)
    hass.states.async_remove(OLD)
    reg.async_update_entity(new, new_entity_id=OLD)
    hass.states.async_set(OLD, "0.5", ATTRS)
    freezer.move_to(p0 + 2 * period + timedelta(minutes=3))
    hass.states.async_set(OLD, "2", ATTRS)
    await async_wait_recording_done(hass)
    await _compile(hass, p0 + 2 * period)

    assert await _sums(hass, p0) == [10.0, 15.0, 17.0]


@pytest.mark.parametrize("old_meter_unavailable", [False, True])
async def test_swap_corrects_the_jump_of_a_used_meter(
    recorder_mock: Recorder,
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    old_meter_unavailable: bool,
) -> None:
    """A used plug at 50 kWh replaces a meter at 115 kWh: the sum must not jump.

    That also holds when the old meter is already unplugged at the swap: then the
    reading the recorder compiled last is the base.
    """
    await async_setup_component(hass, "sensor", {})
    dev_reg = dr.async_get(hass)
    reg = er.async_get(hass)
    devices = {}
    for name in ("zha", "matter"):
        entry = MockConfigEntry(domain=name)
        entry.add_to_hass(hass)
        devices[name] = dev_reg.async_get_or_create(
            config_entry_id=entry.entry_id, identifiers={(name, "plug")}
        ).id
    reg.async_get_or_create(
        "sensor",
        "zha",
        "old-plug",
        device_id=devices["zha"],
        suggested_object_id="washer_energy",
        capabilities={"state_class": "total_increasing"},
    )
    new = reg.async_get_or_create(
        "sensor",
        "matter",
        "new-plug",
        device_id=devices["matter"],
        suggested_object_id="new_plug_energy",
    ).entity_id

    p0 = dt_util.utcnow().replace(minute=0, second=0, microsecond=0) + timedelta(
        hours=1
    )
    period = timedelta(minutes=5)
    freezer.move_to(p0 + timedelta(minutes=1))
    hass.states.async_set(OLD, "100", ATTRS)
    hass.states.async_set(new, "50", ATTRS)
    freezer.move_to(p0 + timedelta(minutes=3))
    hass.states.async_set(OLD, "110", ATTRS)
    freezer.move_to(p0 + period + timedelta(minutes=1))
    hass.states.async_set(OLD, "115", ATTRS)
    await async_wait_recording_done(hass)
    await _compile(hass, p0)
    await _compile(hass, p0 + period)

    freezer.move_to(p0 + 2 * period + timedelta(minutes=1))
    if old_meter_unavailable:
        hass.states.async_set(OLD, "unavailable", {"friendly_name": "Washer"})
    manager = SwapManager(hass)
    plan = await async_plan(hass, devices["zha"], devices["matter"], [(OLD, new)])
    await manager.async_apply(plan)
    # What the integrations do: the old entity is gone, the new one reports.
    hass.states.async_set(OLD, "50.5", ATTRS)
    freezer.move_to(p0 + 2 * period + timedelta(minutes=3))
    hass.states.async_set(OLD, "52", ATTRS)
    await async_wait_recording_done(hass)
    await _compile(hass, p0 + 2 * period)
    assert await _sums(hass, p0) == [10.0, 15.0, 67.0]

    assert len(manager.pending) == 1
    assert await async_try_apply(hass, manager.pending[0]) is True
    await async_wait_recording_done(hass)

    assert await _sums(hass, p0) == [10.0, 15.0, 17.0]
    manager.async_unload()
