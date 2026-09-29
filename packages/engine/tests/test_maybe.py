"""ADR-003: unknown must not silently become zero or False."""

import pytest

from engine import AssumptionLog, Maybe, UnknownValueError


def test_unknown_has_no_truth_value():
    # The whole point: `if contract.trade_kicker:` must not read as False.
    with pytest.raises(TypeError, match="no truth value"):
        bool(Maybe.unknown())


def test_absent_also_has_no_truth_value():
    with pytest.raises(TypeError):
        bool(Maybe.absent())


def test_require_raises_on_unknown():
    with pytest.raises(UnknownValueError, match="unknown"):
        Maybe.unknown().require("trade kicker")


def test_require_returns_known_value():
    assert Maybe.known(0.15).require() == 0.15


def test_or_absent_distinguishes_absent_from_unknown():
    assert Maybe.absent().or_absent(0.0) == 0.0
    with pytest.raises(UnknownValueError):
        Maybe.unknown().or_absent(0.0)


def test_assume_on_unknown_records_an_assumption():
    log = AssumptionLog()
    value = log.read(
        Maybe.unknown(),
        0.0,
        "C.J. McCollum",
        "trade_kicker_pct",
        "not verifiable from available sources",
    )
    assert value == 0.0
    assert len(log) == 1
    assert "C.J. McCollum" in log.entries[0].describe()


def test_assume_on_known_records_nothing():
    log = AssumptionLog()
    assert log.read(Maybe.known(0.15), 0.0, "x", "trade_kicker_pct", "r") == 0.15
    assert log.is_empty


def test_assume_on_absent_records_nothing():
    # A genuine absence is knowledge, not a guess.
    log = AssumptionLog()
    assert log.read(Maybe.absent(), 0.0, "x", "trade_kicker_pct", "r") == 0.0
    assert log.is_empty
