"""Disagreements must be recorded, not silently resolved."""

from nbadata.ingest.precedence import Src
from nbadata.ingest.reconcile import Reconciler


def test_agreeing_sources_produce_no_disagreement():
    r = Reconciler()
    got = r.resolve(
        "birth_date", "nikola jokic", {Src.BBREF_ROSTER: "1995-02-19", Src.FANSPO: "1995-02-19"}
    )
    assert got == "1995-02-19"
    assert r.summary["disagreements"] == 0
    assert r.summary["agreements"] == 1


def test_conflicting_sources_are_recorded_with_the_losing_value():
    r = Reconciler()
    got = r.resolve(
        "birth_date", "someone", {Src.BBREF_ROSTER: "1995-02-19", Src.FANSPO: "1995-02-20"}
    )
    assert got == "1995-02-19"  # precedence picks B-R
    assert r.summary["disagreements"] == 1
    assert r.disagreements[0].others == {"fanspo": "1995-02-20"}


def test_missing_values_are_skipped_not_treated_as_conflicts():
    r = Reconciler()
    got = r.resolve("birth_date", "x", {Src.BBREF_ROSTER: None, Src.FANSPO: "1999-01-01"})
    assert got == "1999-01-01"
    assert r.summary["disagreements"] == 0


def test_all_sources_empty_yields_nothing():
    r = Reconciler()
    assert r.resolve("birth_date", "x", {Src.FANSPO: None, Src.BBREF_ROSTER: ""}) is None
