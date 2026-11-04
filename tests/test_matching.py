"""Tests for pairing old and new entities."""

from custom_components.nine_lives.matching import (
    EntityInfo,
    fits,
    functions_match,
    main_functions,
    propose_pairs,
)


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


def test_appended_numbers_do_not_hide_the_end_of_the_id() -> None:
    old = [_e("button.plug_eu_identify_2")]
    new = [_e("button.new_plug_identify", "identify")]

    assert len(propose_pairs(old, new).pairs) == 1


def test_fits_follows_the_pairing_rules() -> None:
    temperature = _e("sensor.a_temperature", "temperature", "°C")
    assert fits(temperature, _e("sensor.b_temperature", "temperature", "°C"))
    assert not fits(temperature, _e("sensor.b_humidity", "humidity", "%"))
    assert not fits(_e("light.a"), _e("switch.b"))


def test_main_functions_skip_diagnostics_settings_and_controls() -> None:
    entities = [
        _e("light.lamp"),
        _e("update.lamp", "firmware"),
        _e("button.lamp_identify", "identify"),
        EntityInfo("number.lamp_level", "reg", category="config"),
        EntityInfo("sensor.lamp_uptime", "reg", "uptime", category="diagnostic"),
    ]
    assert main_functions(entities) == [("light", None)]


def test_functions_match() -> None:
    light = [("light", None)]
    assert functions_match(light, light)
    assert functions_match([], [])
    assert not functions_match([], light)
    assert not functions_match(light, [("switch", None)])
    # A plug may call its switch an outlet, the replacement may not.
    assert functions_match([("switch", "outlet")], [("switch", None)])
    assert not functions_match([("sensor", "temperature")], [("sensor", "humidity")])
    # One function in common is enough, the pairs are checked one by one.
    assert functions_match(
        [("sensor", "temperature"), ("sensor", "humidity")],
        [("sensor", "temperature"), ("binary_sensor", "motion")],
    )
