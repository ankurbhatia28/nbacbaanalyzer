"""
The answer card (tasks 7.2, 7.3, 7.6), built from hand-made verdicts.

No PDF, no database, no key: a card is a pure function of a verdict, so it is
tested as one. What matters is that nothing the audit found is lost on the way
to the reader -- an unverified figure, an unknown value, an undated row -- and
that the card shows the words and the query a conclusion rests on.
"""

from __future__ import annotations

import json

from agent.answer import Verdict
from agent.card import SCHEMA_VERSION, Status, WarningKind, build
from agent.router import Intent, Routing
from nbadata.query import Snapshot

PROVISION = {
    "found": True,
    "citation_requested": "Art. VII §6(j)(1)",
    "citation_returned": "Art. VII §6(j)(1)",
    "substituted": False,
    "passages": [
        {
            "citation": "Art. VII §6(j)(1)",
            "pdf_page": 264,
            "printed_page": 240,
            "text": "(1) ... 100% of the Traded Player's ... plus $250,000 ...",
        }
    ],
}

SEARCH = {
    "passages": [
        {"citation": "Art. VII §8", "text": "matched text", "is_evidence": True},
        {"citation": "Art. I §1(a)", "text": "context only", "is_evidence": False},
    ]
}


def query(rows, provenance=None):
    return {
        "ok": True,
        "columns": list(rows[0]) if rows else [],
        "rows": rows,
        "row_count": len(rows),
        "sql": 'SELECT SUM(y.cap_figure) AS "sum_salary" FROM ... WHERE c.team_key = ?',
        "params": ["DEN"],
        "provenance": provenance
        or [
            {
                "source": "bbref_contracts",
                "rows": 14,
                "basis": "scraped",
                "earliest": "2026-09-29",
                "latest": "2026-09-29",
            }
        ],
    }


def verdict(text="", calls=(), **kw):
    v = Verdict(question="q", text=text, **kw)
    v.tool_calls = list(calls)
    if "citations" not in kw:
        v.citations = tuple(
            r.get("citation_returned") for _, _, r in v.tool_calls if r.get("citation_returned")
        )
    return v


def test_a_card_quotes_the_text_verbatim_with_its_page():
    card = build(
        verdict(
            "The Standard exception permits 100% plus $250,000 (Art. VII §6(j)(1)).",
            [("fetch_provision", {}, PROVISION)],
        )
    )
    (quote,) = card.quotes
    assert quote.text == PROVISION["passages"][0]["text"]
    assert (quote.pdf_page, quote.printed_page) == (264, 240)
    assert quote.cited_in_answer
    assert card.status is Status.ANSWERED
    assert card.verified


def test_context_passages_are_not_shown_as_evidence():
    card = build(verdict("See Art. VII §8.", [("search_cba", {}, SEARCH)], citations=("x",)))
    assert [q.citation for q in card.quotes] == ["Art. VII §8"]


def test_quotes_the_answer_names_come_first():
    other = json.loads(json.dumps(PROVISION))
    other["passages"][0]["citation"] = "Art. VII §2"
    card = build(
        verdict(
            "Per Art. VII §6(j)(1).",
            [("fetch_provision", {}, other), ("fetch_provision", {}, PROVISION)],
        )
    )
    assert [q.citation for q in card.quotes] == ["Art. VII §6(j)(1)", "Art. VII §2"]


def test_every_figure_carries_its_query_and_provenance():
    card = build(
        verdict(
            "Denver is committed for $221,069,148.",
            [("query_league_data", {}, query([{"sum_salary": 221069148}]))],
            citations=("data",),
        )
    )
    (figure,) = card.figures
    assert figure.params == ["DEN"]
    assert "SUM" in figure.sql
    assert figure.provenance[0]["basis"] == "scraped"
    assert figure.in_answer == ["$221,069,148"]


def test_a_failed_query_is_not_shown_as_a_figure():
    card = build(verdict("x", [("query_league_data", {}, {"ok": False, "error": "bad"})]))
    assert card.figures == []


def test_unsourced_figures_reach_the_card_as_a_warning_and_unverify_it():
    card = build(
        verdict(
            "It is $31,000,000.",
            [("fetch_provision", {}, PROVISION)],
            unsourced_figures=("$31,000,000",),
        )
    )
    assert not card.verified
    (warning,) = card.warnings
    assert warning.kind is WarningKind.UNSOURCED_FIGURES
    assert warning.detail == ["$31,000,000"]


def test_an_answer_citing_nothing_is_flagged_unsupported():
    card = build(verdict("The rule says so."))
    assert not card.verified
    assert [w.kind for w in card.warnings] == [WarningKind.UNSUPPORTED]


def test_an_unknown_value_is_a_warning_not_a_detail_in_a_table():
    """ADR-003: unknown must be visible as unknown."""
    rows = [{"player": "A", "guarantee_kind": "unknown"}]
    card = build(verdict("x", [("query_league_data", {}, query(rows))], citations=("c",)))
    (warning,) = card.warnings
    assert warning.kind is WarningKind.UNKNOWN_VALUES
    assert warning.detail == ["guarantee_kind"]


def test_undated_rows_are_called_out():
    undated = [{"source": "spotrac_archive", "rows": 1, "basis": "undated"}]
    card = build(
        verdict("x", [("query_league_data", {}, query([{"a": 1}], undated))], citations=("c",))
    )
    assert [w.kind for w in card.warnings] == [WarningKind.UNDATED_ROWS]


def test_running_out_of_rounds_is_a_warning():
    card = build(
        verdict("x", [("fetch_provision", {}, PROVISION)], exhausted_rounds=True),
    )
    assert WarningKind.EXHAUSTED_ROUNDS in [w.kind for w in card.warnings]


def test_a_refusal_carries_the_decision_it_rests_on():
    routing = Routing(intents=(Intent.REFUSED,), reason="past season", refusal_basis="historical")
    card = build(verdict("Declined.", refused=True, routing=routing))
    assert card.status is Status.REFUSED
    assert card.refusal_basis is not None and "D6" in card.refusal_basis
    assert card.warnings == []


def test_a_partial_refusal_answers_and_still_says_why_part_was_declined():
    routing = Routing(intents=(Intent.RULES, Intent.REFUSED), reason="r", refusal_basis="opinion")
    card = build(
        verdict("Per Art. VII §6(j)(1).", [("fetch_provision", {}, PROVISION)], routing=routing)
    )
    assert card.status is Status.ANSWERED
    assert card.refusal_basis is not None and "D10" in card.refusal_basis


def test_a_cap_refusal_is_unavailable_with_the_reason():
    card = build(verdict("I cannot take that request right now: rate limit", over_budget="rate"))
    assert card.status is Status.UNAVAILABLE


def test_an_empty_answer_is_unavailable_not_answered():
    """The round-cap bug from 6.9: fourteen citations and no text read as success."""
    card = build(verdict("", [("fetch_provision", {}, PROVISION)]))
    assert card.status is Status.UNAVAILABLE
    assert not card.verified


def test_the_card_serialises_to_plain_json_with_the_dataset_and_schema():
    snap = Snapshot(
        built_at="2026-10-02", season="2026-2027", source_dates={"fanspo": "2026-09-29"}
    )
    card = build(verdict("Per Art. VII §6(j)(1).", [("fetch_provision", {}, PROVISION)]), snap)
    payload = json.loads(json.dumps(card.to_json()))
    assert payload["schema"] == SCHEMA_VERSION
    assert payload["dataset"]["source_dates"] == {"fanspo": "2026-09-29"}
    assert payload["status"] == "answered"
    assert payload["quotes"][0]["printed_page"] == 240
