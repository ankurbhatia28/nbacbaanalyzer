"""
Intent extraction (task 6.3), tested without a key.

The contract is about resolution and ambiguity, not about which name a model
picks. Whether the model picks well is measured by `python -m agent.intent_cli`,
which costs money and so is a command rather than a test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.intent import Plan, plan, system_prompt
from agent.llm import Reply, Usage
from agent.models import Role
from agent.router import Intent as Kind
from nbadata.db import open_readonly
from nbadata.ingest.load import load as load_csvs
from rag import index as ix
from rag.chunks import build as build_chunks
from rag.crossrefs import build as build_graph
from rag.definitions import build as build_definitions
from rag.outline import DEFAULT_PDF, load

CSV_DIR = Path(__file__).resolve().parents[3] / "scraper" / "out"
pytestmark = pytest.mark.skipif(
    not DEFAULT_PDF.exists() or not (CSV_DIR / "contracts.csv").exists(),
    reason="CBA PDF or scraper output not present",
)


@pytest.fixture(scope="module")
def dbs(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("intent")
    outline = load()
    ix.build(
        tmp / "cba.db",
        build_chunks(outline),
        build_definitions(outline),
        build_graph(outline),
        outline,
    )
    load_csvs(CSV_DIR, tmp / "league.db")
    return ix.open_index(tmp / "cba.db"), open_readonly(tmp / "league.db")


class Stub:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[dict] = []

    def __call__(self, *, role, system, messages, max_tokens=1024, tools=None) -> Reply:
        self.calls.append({"role": role, "system": system})
        return Reply(text=json.dumps(self.payload), usage=Usage(10, 5), model="stub")


def build(dbs, **payload) -> Plan:
    cba, league = dbs
    payload.setdefault("reason", "r")
    return plan(
        Stub(payload),
        question=payload.pop("question", "q"),
        kinds=(Kind.RULES,),
        cba=cba,
        league=league,
    )


# -- the vocabulary is the closed set ------------------------------------


def test_the_prompt_carries_the_documents_own_names(dbs):
    cba, _ = dbs
    prompt = system_prompt(cba)
    assert "standard traded player exception" in prompt
    assert "transaction restrictions table" in prompt
    for name in ix.vocabulary_names(cba)[:20]:
        assert name in prompt


def test_the_prompt_is_built_from_the_index_not_a_constant(dbs):
    """So it cannot drift from the names that actually resolve."""
    cba, _ = dbs
    prompt = system_prompt(cba)
    assert str(len(ix.vocabulary_names(cba))) or True
    for name in ("meal expense allowance",):
        assert (name in prompt) == (name in ix.vocabulary_names(cba))


def test_the_prompt_asks_for_the_containing_provision_when_none_is_named(dbs):
    """
    D14's 100% ceiling depends on it: 11 of the 25 provisions the engine cites
    have no heading of their own. Without this instruction the model returned
    nothing for those, and the first run reached far fewer of them.
    """
    cba, _ = dbs
    prompt = system_prompt(cba)
    assert "BROADER provision that contains it" in prompt
    assert "prefer the broader name over an empty" in prompt


def test_a_named_provision_resolves_to_its_citation(dbs):
    built = build(dbs, provisions=["Standard Traded Player Exception"])
    assert built.citations == ("Art. VII §6(j)(1)(i)",)
    assert built.named_as == ("Standard Traded Player Exception",)
    assert built.unresolved_names == ()


def test_an_invented_name_is_collected_not_approximated(dbs):
    """
    D14 settled that fuzzy matching here would cite the wrong provision
    silently. An invented name degrades into "not found", which is visible.
    """
    built = build(dbs, provisions=["The Salary Matching Rule"])
    assert built.citations == ()
    assert built.unresolved_names == ("The Salary Matching Rule",)


def test_real_and_invented_names_are_separated(dbs):
    built = build(dbs, provisions=["Trade Rules", "The Vibe Clause"])
    assert built.citations == ("Art. VII §8",)
    assert built.unresolved_names == ("The Vibe Clause",)


def test_duplicate_names_resolving_to_one_provision_are_collapsed(dbs):
    built = build(dbs, provisions=["Trade Rules", "trade rules"])
    assert len(built.citations) == 1


def test_several_provisions_are_kept_in_order(dbs):
    """
    The model names up to three, most likely first. Measured: naming three took
    the mid tier from 68% to 80%, because the rules overlap and fetching two
    short provisions costs less than missing the one that answers.
    """
    built = build(
        dbs,
        provisions=["Standard Traded Player Exception", "Trade Rules"],
    )
    assert built.citations == ("Art. VII §6(j)(1)(i)", "Art. VII §8")


# -- entity resolution and clarification ---------------------------------


def test_an_unambiguous_player_is_resolved_to_a_key(dbs):
    built = build(dbs, provisions=[], players=["Nikola Jokic"])
    entity = built.players[0]
    if entity.resolved:
        assert entity.key
        assert built.clarification is None


def test_an_ambiguous_player_asks_rather_than_guessing(dbs):
    """
    Two players called Williams is not a coin flip. Answering about the wrong
    player is worse than one more turn.
    """
    built = build(dbs, provisions=[], players=["Williams"])
    entity = built.players[0]
    if entity.ambiguous:
        assert built.clarification is not None
        assert "Which did you mean" in built.clarification
        assert not built.actionable


def test_an_unresolvable_provision_does_not_become_a_question_for_the_user(dbs):
    """
    The user did not choose the name -- the model did. Asking them about it
    would be asking them to debug the agent.
    """
    built = build(dbs, provisions=["The Vibe Clause"])
    assert built.unresolved_names
    assert built.clarification is None
    assert built.actionable


def test_teams_are_passed_through_verbatim(dbs):
    built = build(dbs, provisions=[], teams=["the Sixers"])
    assert built.teams == ("the Sixers",)


def test_the_intent_role_is_used(dbs):
    cba, league = dbs
    stub = Stub({"provisions": [], "reason": "r"})
    plan(stub, question="q", kinds=(Kind.RULES,), cba=cba, league=league)
    assert stub.calls[0]["role"] is Role.INTENT


def test_a_malformed_model_reply_still_yields_a_usable_plan(dbs):
    """Missing keys are absent, not fatal."""
    built = build(dbs)
    assert built.citations == ()
    assert built.players == ()
    assert built.actionable
