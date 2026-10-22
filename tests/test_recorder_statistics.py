"""How long-term statistics behave when a successor takes over a meter's entity ID.

Energy meters keep a running sum. When a new meter starting at 0 continues the old
meter's statistics, the drop must count as a meter reset, not as negative consumption.
"""

from datetime import datetime, timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.recorder import Recorder, get_instance
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
    do_adhoc_statistics,
    statistics_during_period,
)

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
