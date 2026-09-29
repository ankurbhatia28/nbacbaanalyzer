"""The emitted JSON Schema is the shared contract (task 1.13)."""

import json

from engine.schema import build_schema


def test_schema_covers_the_root_types():
    defs = build_schema()["$defs"]
    for name in (
        "Season",
        "Contract",
        "ContractYear",
        "TeamState",
        "DraftPick",
        "TradeException",
        "CapHold",
        "HardCapCeiling",
    ):
        assert name in defs, name


def test_maybe_is_tri_state_not_nullable():
    """
    A nullable number would erase the difference between 'absent' and
    'unknown' -- exactly the distinction ADR-003 exists to keep.
    """
    prop = build_schema()["$defs"]["Contract"]["properties"]["trade_kicker_pct"]
    assert prop["type"] == "object"
    assert prop["properties"]["state"]["enum"] == ["known", "absent", "unknown"]


def test_enums_are_emitted_as_value_lists():
    defs = build_schema()["$defs"]
    assert "2W" in defs["ContractType"]["enum"]
    assert set(defs["ApronLevel"]["enum"]) == {"first_apron", "second_apron"}


def test_required_fields_exclude_those_with_defaults():
    contract = build_schema()["$defs"]["Contract"]
    assert "player_id" in contract["required"]
    assert "trade_kicker_pct" not in contract["required"]


def test_schema_is_json_serialisable():
    json.dumps(build_schema())
