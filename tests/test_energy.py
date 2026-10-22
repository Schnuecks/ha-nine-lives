"""Tests for the meter sum corrections."""

from datetime import UTC, datetime

import pytest
from homeassistant.core import State

from custom_components.meshmove.energy import pending_adjustment, transition_step

WHEN = datetime(2026, 10, 22, 15, 47, 21, tzinfo=UTC)


@pytest.mark.parametrize(
    ("state_class", "previous", "new", "expected"),
    [
        # A new meter far below the old one: Home Assistant sees a reset.
        ("total_increasing", 115.0, 50.0, 50.0),
        ("total_increasing", 115.0, 0.0, 0.0),
        # Above the old value or a small dip: counted as a change.
        ("total_increasing", 115.0, 300.0, 185.0),
        ("total_increasing", 115.0, 110.0, -5.0),
        ("total", 115.0, 50.0, -65.0),
    ],
)
def test_transition_step(state_class, previous, new, expected) -> None:
    assert transition_step(state_class, previous, new) == expected


def test_total_with_new_last_reset_counts_from_zero() -> None:
    assert transition_step("total", 115.0, 50.0, "2026-01-01", "2026-10-01") == 50.0


def _state(value, unit="kWh", state_class="total_increasing", **attrs):
    return State(
        "sensor.x",
        str(value),
        {"state_class": state_class, "unit_of_measurement": unit, **attrs},
    )


def test_pending_adjustment_undoes_the_step() -> None:
    item = pending_adjustment("sensor.washer", _state(115), _state(50), WHEN)

    assert item == {
        "statistic_id": "sensor.washer",
        "period_start": "2026-10-22T15:45:00+00:00",
        "adjustment": -50.0,
        "unit": "kWh",
    }


def test_units_are_converted() -> None:
    item = pending_adjustment(
        "sensor.washer", _state(115000, unit="Wh"), _state(50), WHEN
    )

    assert item["adjustment"] == -50.0
    assert item["unit"] == "kWh"


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (_state(21.5, "°C", "measurement"), _state(22.0, "°C", "measurement")),
        (_state("unavailable"), _state(50)),
        (_state(115), _state(115)),
        (_state(115, unit="kWh"), _state(50, unit="m³")),
        (None, _state(50)),
    ],
)
def test_no_adjustment_needed_or_possible(before, after) -> None:
    assert pending_adjustment("sensor.x", before, after, WHEN) is None
