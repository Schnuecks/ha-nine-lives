"""Tests for rewriting device references."""

from custom_components.nine_lives.references import rewrite

ID_MAP = {"olddevice": "newdevice", "oldentity": "newentity"}


def test_rewrites_targets_and_device_automations() -> None:
    config = {
        "id": "1",
        "triggers": [
            {
                "trigger": "device",
                "device_id": "olddevice",
                "entity_id": "oldentity",
                "domain": "sensor",
                "type": "temperature",
                "above": 25,
            }
        ],
        "actions": [
            {"action": "light.turn_on", "target": {"device_id": ["olddevice", "x"]}},
            {"action": "notify.phone", "data": {"message": "olddevice is not an ID"}},
        ],
    }

    result = rewrite(config, ID_MAP, entity_domains={"newentity": "sensor"})

    assert result.config["triggers"][0]["device_id"] == "newdevice"
    assert result.config["triggers"][0]["entity_id"] == "newentity"
    assert result.config["actions"][0]["target"]["device_id"] == ["newdevice", "x"]
    assert result.config["actions"][1]["data"]["message"] == "olddevice is not an ID"
    assert [c.path for c in result.changes] == [
        "triggers[0].device_id",
        "triggers[0].entity_id",
        "actions[0].target.device_id[0]",
    ]
    assert result.reviews == []
    # The input is left untouched, so it can serve as the backup.
    assert config["triggers"][0]["device_id"] == "olddevice"


def test_integration_specific_trigger_needs_review() -> None:
    config = {
        "triggers": [
            {
                "platform": "device",
                "device_id": "olddevice",
                "domain": "zha",
                "type": "remote_button_short_press",
                "subtype": "turn_on",
            }
        ],
        "conditions": [
            {
                "condition": "device",
                "device_id": "olddevice",
                "domain": "zha",
                "type": "is_on",
            }
        ],
    }

    result = rewrite(config, ID_MAP, new_integrations={"matter"})

    assert [(r.path, r.reason) for r in result.reviews] == [
        ("triggers[0]", "device trigger 'remote_button_short_press' of zha"),
        ("conditions[0]", "device condition 'is_on' of zha"),
    ]


def test_same_integration_needs_no_review() -> None:
    config = [
        {
            "device_id": "olddevice",
            "domain": "zha",
            "type": "remote_button_short_press",
        }
    ]

    result = rewrite(config, ID_MAP, new_integrations={"zha"})

    assert result.reviews == []
    assert result.config[0]["device_id"] == "newdevice"


def test_unrelated_config_is_unchanged() -> None:
    config = {"sequence": [{"delay": 5}, {"device_id": "otherdevice"}]}

    result = rewrite(config, ID_MAP)

    assert result.config == config
    assert result.changes == result.reviews == []
