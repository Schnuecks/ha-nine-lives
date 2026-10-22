"""Tests for pairing old and new entities."""

from custom_components.nine_lives.matching import EntityInfo, propose_pairs


def _e(entity_id, device_class=None, unit=None, state_class=None, name=None):
    return EntityInfo(
        entity_id, f"reg-{entity_id}", device_class, unit, state_class, name
    )


def test_pairs_by_device_class_not_by_order() -> None:
    old = [
        _e("sensor.aqara_temperature", "temperature", "°C", "measurement"),
        _e("sensor.aqara_humidity", "humidity", "%", "measurement"),
        _e("sensor.aqara_battery", "battery", "%", "measurement"),
    ]
    new = [
        _e("sensor.ikea_battery", "battery", "%", "measurement"),
        _e("sensor.ikea_humidity", "humidity", "%", "measurement"),
        _e("sensor.ikea_temperature", "temperature", "°C", "measurement"),
    ]

    result = propose_pairs(old, new)

    assert [(o.entity_id, n.entity_id) for o, n in result.pairs] == [
        ("sensor.aqara_temperature", "sensor.ikea_temperature"),
        ("sensor.aqara_humidity", "sensor.ikea_humidity"),
        ("sensor.aqara_battery", "sensor.ikea_battery"),
    ]
    assert result.unmatched_old == result.unmatched_new == []


def test_never_pairs_different_domains_or_device_classes() -> None:
    old = [_e("sensor.old_temperature", "temperature"), _e("light.old_lamp")]
    new = [_e("sensor.new_humidity", "humidity"), _e("switch.new_plug")]

    result = propose_pairs(old, new)

    assert result.pairs == []
    assert len(result.unmatched_old) == 2
    assert len(result.unmatched_new) == 2


def test_leftovers_are_reported() -> None:
    old = [_e("sensor.old_temperature", "temperature"), _e("sensor.old_lqi")]
    new = [
        _e("sensor.new_temperature", "temperature"),
        _e("sensor.new_illuminance", "illuminance", "lx"),
    ]

    result = propose_pairs(old, new)

    assert [(o.entity_id, n.entity_id) for o, n in result.pairs] == [
        ("sensor.old_temperature", "sensor.new_temperature"),
    ]
    assert [o.entity_id for o in result.unmatched_old] == ["sensor.old_lqi"]
    assert [n.entity_id for n in result.unmatched_new] == ["sensor.new_illuminance"]


def test_one_sided_device_class_needs_matching_unit() -> None:
    old = [_e("sensor.old_power", unit="W")]
    new = [_e("sensor.new_power", "power", "W")]

    assert len(propose_pairs(old, new).pairs) == 1


def test_missing_device_class_prefers_matching_unit() -> None:
    old = [_e("sensor.old_power", unit="W")]
    new = [_e("sensor.new_energy", unit="kWh"), _e("sensor.new_power", unit="W")]

    result = propose_pairs(old, new)

    assert result.pairs[0][1].entity_id == "sensor.new_power"
    assert [n.entity_id for n in result.unmatched_new] == ["sensor.new_energy"]
