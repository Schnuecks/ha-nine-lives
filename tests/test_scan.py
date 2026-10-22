"""Tests for the reference search and ID suggestions."""

import pytest

from custom_components.nine_lives.scan import is_referenced, suggested_entity_id


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("entity_id: sensor.plug_energy", True),
        ("{{ states('sensor.plug_energy') }}", True),
        ('["sensor.plug_energy"]', True),
        ("sensor.plug_energy_2", False),
        # Templates name entities as states.sensor.x, with attributes after it.
        ("{{ states.sensor.plug_energy.attributes.unit }}", True),
        ("my_sensor.plug_energy", False),
    ],
)
def test_is_referenced_matches_whole_ids(text, expected) -> None:
    assert is_referenced("sensor.plug_energy", [text]) is expected


@pytest.mark.parametrize(
    ("entity_id", "name", "expected"),
    [
        (
            "button.strom_anker_identifizieren",
            "Strom Prusa Identifizieren",
            "button.strom_prusa_identifizieren",
        ),
        ("switch.strom_prusa", "Strom Prusa", None),
        ("switch.strom_prusa", None, None),
        ("switch.strom_prusa", "", None),
    ],
)
def test_suggested_entity_id(entity_id, name, expected) -> None:
    assert suggested_entity_id(entity_id, name) == expected
