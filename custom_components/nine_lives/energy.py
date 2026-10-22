"""Keep meter sums (energy, gas, water) free of jumps when one meter replaces another.

Home Assistant adds up the changes of a meter. When the new meter takes over the old
meter's statistics, the step from the old meter's last value to the new meter's first
value is counted as well: as a meter reset (the new value counts in full) or as a plain
change. Either way it is not real consumption, so Nine Lives works out that step with
the same rules and subtracts it again once the recorder has compiled the swap's period.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import (
    STATISTIC_UNIT_TO_UNIT_CONVERTER,
    statistics_during_period,
)
from homeassistant.components.sensor import SensorStateClass
from homeassistant.core import HomeAssistant, State
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

PERIOD = timedelta(minutes=5)
# The recorder compiles a period a few seconds after it ends; check a bit later.
CHECK_DELAY = timedelta(seconds=40)
RETRY_DELAY = timedelta(minutes=1)
GIVE_UP_AFTER = timedelta(days=1)
_SUM_CLASSES = {SensorStateClass.TOTAL, SensorStateClass.TOTAL_INCREASING}


def transition_step(
    state_class: str,
    previous: float,
    new: float,
    previous_last_reset: str | None = None,
    new_last_reset: str | None = None,
) -> float:
    """How much the recorder adds to the sum when the value jumps from previous to new.

    Mirrors the rules in Home Assistant's sensor statistics: a total_increasing meter
    that drops below 90 % of its last value has been reset and counts from 0; a total
    meter is reset when its last_reset changes.
    """
    if state_class == SensorStateClass.TOTAL_INCREASING:
        return new if new < 0.9 * previous else new - previous
    if new_last_reset is not None and new_last_reset != previous_last_reset:
        return new
    return new - previous


def _float(state: State | None) -> float | None:
    try:
        return float(state.state) if state else None
    except ValueError:
        return None


def pending_adjustment(
    statistic_id: str, before: State | None, after: State | None, when: datetime
) -> dict[str, Any] | None:
    """The correction for one meter handing over to another, or None if not needed.

    before is the last state of the meter that hands over, after the first state of the
    meter that takes over the statistic.
    """
    if before is None or after is None:
        return None
    state_class = before.attributes.get("state_class")
    if state_class not in _SUM_CLASSES:
        return None
    previous, new = _float(before), _float(after)
    if previous is None or new is None:
        return None

    unit = after.attributes.get("unit_of_measurement")
    previous_unit = before.attributes.get("unit_of_measurement")
    if previous_unit != unit:
        converter = STATISTIC_UNIT_TO_UNIT_CONVERTER.get(unit)
        if converter is None or previous_unit not in converter.VALID_UNITS:
            _LOGGER.warning(
                "Cannot correct the sum of %s: %s and %s cannot be converted",
                statistic_id,
                previous_unit,
                unit,
            )
            return None
        previous = converter.convert(previous, previous_unit, unit)

    step = transition_step(
        state_class,
        previous,
        new,
        before.attributes.get("last_reset"),
        after.attributes.get("last_reset"),
    )
    if step == 0:
        return None
    period_start = dt_util.as_utc(when).replace(second=0, microsecond=0)
    period_start -= timedelta(minutes=period_start.minute % 5)
    return {
        "statistic_id": statistic_id,
        "period_start": period_start.isoformat(),
        "adjustment": -step,
        "unit": unit,
    }


def next_check(pending: dict[str, Any]) -> datetime:
    """When the recorder should have compiled the period of the swap."""
    return datetime.fromisoformat(pending["period_start"]) + PERIOD + CHECK_DELAY


async def async_try_apply(hass: HomeAssistant, pending: dict[str, Any]) -> bool | None:
    """Apply the correction once its period is compiled.

    Returns True when applied, False to try again later and None to give up.
    """
    start = datetime.fromisoformat(pending["period_start"])
    if dt_util.utcnow() - start > GIVE_UP_AFTER:
        _LOGGER.warning("Gave up correcting the sum of %s", pending["statistic_id"])
        return None
    instance = get_instance(hass)
    rows = await instance.async_add_executor_job(
        statistics_during_period,
        hass,
        start,
        start + PERIOD,
        {pending["statistic_id"]},
        "5minute",
        None,
        {"sum"},
    )
    if not rows.get(pending["statistic_id"]):
        return False
    instance.async_adjust_statistics(
        pending["statistic_id"], start, pending["adjustment"], pending["unit"]
    )
    _LOGGER.info(
        "Corrected the sum of %s by %s %s",
        pending["statistic_id"],
        pending["adjustment"],
        pending["unit"],
    )
    return True
