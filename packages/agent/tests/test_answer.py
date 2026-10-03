"""
The agent loop (tasks 6.4, 6.5, 6.6, 6.7), tested without a key.

The loop's value is in what it refuses to let the model do, so that is what
these tests exercise: refusals that name their basis, clarifications instead of
guesses, and the figure audit that checks the finished answer against what the
tools actually returned.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.answer import MAX_TOOL_ROUNDS, SYSTEM, Verdict, _audit_figures, answer
from agent.llm import Reply, ToolRequest, Usage
from agent.tools import Resources
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
def res(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("loop")
    outline = load()
    ix.build(
        tmp / "cba.db",
        build_chunks(outline),
        build_definitions(outline),
        build_graph(outline),
        outline,
    )
    load_csvs(CSV_DIR, tmp / "league.db")
    return Resources(
        league=open_readonly(tmp / "league.db"),
        cba=ix.open_index(tmp / "cba.db"),
        base_season_cap=136_021_000,
    )


class Script:
    """
    A caller driven by a per-role script, so a whole loop can be replayed.

    Router and intent replies are JSON strings; answer replies are either text
    or a list of tool requests followed by text.
    """

    def __init__(self, *, router: str, intent: str, answers: list) -> None:
        self.router = router
        self.intent = intent
        self.answers = list(answers)
        self.answer_calls = 0
        self.tools_offered: list = []

    def __call__(self, *, role, system, messages, max_tokens=1024, tools=None) -> Reply:
        from agent.models import Role

        if role is Role.ROUTER:
            return Reply(self.router, Usage(10, 5), "stub")
        if role is Role.INTENT:
            return Reply(self.intent, Usage(10, 5), "stub")
        self.answer_calls += 1
        self.tools_offered.append(tools)
        nxt = self.answers.pop(0) if self.answers else "done"
        if isinstance(nxt, list):
            return Reply(
                "",
                Usage(10, 5),
                "stub",
                tool_requests=tuple(
                    ToolRequest(id=f"t{i}", name=n, arguments=a) for i, (n, a) in enumerate(nxt)
                ),
                raw_content=({"type": "text", "text": ""},),
            )
        return Reply(nxt, Usage(10, 5), "stub")


def routing(*intents: str, basis: str | None = None) -> str:
    return json.dumps({"intents": list(intents), "reason": "r", "refusal_basis": basis})


def planning(*provisions: str) -> str:
    return json.dumps({"provisions": list(provisions), "players": [], "teams": [], "reason": "r"})


# -- refusals name the decision they rest on (6.6) ------------------------


def test_a_historical_question_is_refused_citing_the_decision(res):
    verdict = answer(
        Script(router=routing("refused", basis="historical"), intent=planning(), answers=[]),
        question="what was the cap in 2019-20?",
        res=res,
    )
    assert verdict.refused
    assert "past season" in verdict.text
    assert "D6" in verdict.text
    assert verdict.tool_calls == []


def test_an_opinion_question_is_refused_citing_the_decision(res):
    verdict = answer(
        Script(router=routing("refused", basis="opinion"), intent=planning(), answers=[]),
        question="should they trade him?",
        res=res,
    )
    assert verdict.refused
    assert "D10" in verdict.text


def test_a_refusal_with_no_basis_still_explains_itself(res):
    """A refusal that cannot say why is indistinguishable from a bug."""
    verdict = answer(
        Script(router=routing("refused"), intent=planning(), answers=[]),
        question="q",
        res=res,
    )
    assert verdict.refused
    assert "rather say so than guess" in verdict.text


def test_a_partly_refused_question_is_still_answered(res):
    """
    The refusal is carried into the answer turn instead of ending it, because
    declining the whole question would drop the part that is answerable.
    """
    script = Script(
        router=routing("refused", "data", basis="historical"),
        intent=planning(),
        answers=["Here is the current figure; the historical part I cannot answer."],
    )
    verdict = answer(script, question="q", res=res)
    assert not verdict.refused
    assert script.answer_calls == 1


# -- clarification rather than a guess (6.3 in the loop) ------------------


def test_an_ambiguous_player_stops_the_loop_and_asks(res):
    script = Script(
        router=routing("data"),
        intent=json.dumps({"provisions": [], "players": ["Williams"], "teams": [], "reason": "r"}),
        answers=["should not be reached"],
    )
    verdict = answer(script, question="how much is Williams paid?", res=res)
    if verdict.clarification:
        assert "Which did you mean" in verdict.clarification
        assert script.answer_calls == 0
        assert verdict.supported


# -- tools, citations and assumptions (6.7) ------------------------------


def test_citations_are_collected_from_tool_results(res):
    script = Script(
        router=routing("rules"),
        intent=planning("Standard Traded Player Exception"),
        answers=[
            [("fetch_provision", {"citation": "Art. VII §6(j)(1)(i)"})],
            "It permits replacing one traded player.",
        ],
    )
    verdict = answer(script, question="what is the standard TPE?", res=res)
    assert verdict.citations
    assert verdict.supported
    assert any("6(j)(1)" in c for c in verdict.citations)


def test_a_substituted_citation_is_surfaced_as_an_assumption(res):
    """
    The model must not claim to quote §2(e)(2)(i)(A) while holding §2(e)(2)(i),
    so the substitution travels with the answer.
    """
    script = Script(
        router=routing("rules"),
        intent=planning(),
        answers=[
            [("fetch_provision", {"citation": "Art. VII §2(e)(2)(i)(A)"})],
            "A team may not engage in the listed transactions.",
        ],
    )
    verdict = answer(script, question="q", res=res)
    assert any("finer than any indexed passage" in a for a in verdict.assumptions)


def test_a_tool_reporting_not_found_is_surfaced_rather_than_hidden(res):
    script = Script(
        router=routing("rules"),
        intent=planning(),
        answers=[
            [("define_term", {"term": "hard cap"})],
            "The Agreement does not define that term.",
        ],
    )
    verdict = answer(script, question="what is a hard cap?", res=res)
    assert any("not a term this Agreement defines" in a for a in verdict.assumptions)


def test_an_answer_citing_nothing_is_not_supported(res):
    script = Script(router=routing("rules"), intent=planning(), answers=["Trust me."])
    verdict = answer(script, question="q", res=res)
    assert verdict.citations == ()
    assert not verdict.supported
    assert not verdict.trustworthy


def test_the_loop_stops_calling_tools_eventually(res):
    """
    A loop that has lost its way should stop costing money rather than run on.
    """
    forever = [[("define_term", {"term": "Salary"})] for _ in range(MAX_TOOL_ROUNDS + 4)]
    script = Script(router=routing("rules"), intent=planning(), answers=forever)
    verdict = answer(script, question="q", res=res)
    assert verdict.rounds == MAX_TOOL_ROUNDS
    # One more call than rounds: with the budget gone, the model is asked once
    # more with no tools offered, so it has to answer from what it gathered.
    assert script.answer_calls == MAX_TOOL_ROUNDS + 1
    assert verdict.exhausted_rounds


def test_running_out_of_rounds_still_produces_an_answer(res):
    """
    Found against the live API: the loop exhausted its rounds with a last reply
    that only asked for more tools, so the user got fourteen citations, no
    answer, and `trustworthy=True` -- success reported for nothing.
    """
    forever = [[("define_term", {"term": "Salary"})] for _ in range(MAX_TOOL_ROUNDS)]
    script = Script(
        router=routing("rules"),
        intent=planning(),
        answers=[*forever, "Here is what I found."],
    )
    verdict = answer(script, question="q", res=res)
    assert verdict.exhausted_rounds
    assert verdict.text == "Here is what I found."
    assert verdict.answered
    assert f"{MAX_TOOL_ROUNDS}-tool-call budget ran out" in verdict.render()


def test_the_final_forced_call_is_offered_no_tools(res):
    """
    Otherwise it would ask for more, which is the thing that ran out.
    """
    forever = [[("define_term", {"term": "Salary"})] for _ in range(MAX_TOOL_ROUNDS)]
    script = Script(router=routing("rules"), intent=planning(), answers=[*forever, "done"])
    answer(script, question="q", res=res)
    assert script.tools_offered[-1] is None, "the last call must offer no tools"
    assert script.tools_offered[0] is not None


def test_an_empty_answer_is_never_trustworthy(res):
    """
    An answer that does not exist cannot be trustworthy, however well cited the
    run was. `trustworthy` is the single property a caller checks.
    """
    script = Script(
        router=routing("rules"),
        intent=planning(),
        answers=[[("fetch_provision", {"citation": "Art. VII §8"})], "   "],
    )
    verdict = answer(script, question="q", res=res)
    assert verdict.citations, "the run did gather citations"
    assert verdict.supported
    assert not verdict.answered
    assert not verdict.trustworthy


def test_a_model_failure_returns_a_verdict_rather_than_raising(res):
    class Broken:
        def __call__(self, *, role, system, messages, max_tokens=1024, tools=None):
            return Reply("not json", Usage(1, 1), "stub")

    verdict = answer(Broken(), question="q", res=res)
    assert "could not interpret" in verdict.text
    assert not verdict.refused


# -- the figure audit (5.9, enforced rather than requested) --------------


def test_an_invented_figure_is_flagged():
    assert _audit_figures("the limit is $7,500,000", set(), set()) == ("$7,500,000",)


def test_a_figure_quoted_from_cited_text_is_not_flagged():
    """
    5.9 forbids computing or recalling a figure, not quoting one out of the
    provision just cited -- the most defensible thing an answer can do. An
    earlier version flagged "$250,000" inside a verbatim quotation of
    Art. VII §6(j)(1)(i), and a warning that fires on the right answer teaches
    readers to ignore it.
    """
    assert _audit_figures("100% plus $250,000", set(), {"$250,000", "100%"}) == ()


def test_a_figure_from_a_database_row_is_not_flagged():
    assert _audit_figures("committed $221,069,148", {"221,069,148"}, set()) == ()


def test_formatting_differences_are_not_treated_as_fabrication():
    """Normalised on digits, so $221,069,148 matches a raw 221069148."""
    assert _audit_figures("$221,069,148", {"221069148"}, set()) == ()


def test_small_counts_and_spans_are_ignored():
    assert _audit_figures("within 3 days, two of the 15 teams", set(), set()) == ()


def test_the_audit_does_not_ask_a_model_whether_the_model_cheated():
    """
    It is a set comparison over digits. Nothing in it consults a model, which
    is the point: a guardrail a model can talk its way past is not one.
    """
    verdict = Verdict(question="q", text="$9,999,999", citations=("Art. VII §8",))
    verdict.unsourced_figures = _audit_figures(verdict.text, set(), set())
    assert verdict.supported
    assert not verdict.trustworthy
    assert "UNVERIFIED FIGURES" in verdict.render()


# -- the prompt states the prohibitions ---------------------------------


def test_the_system_prompt_forbids_calculation_and_unaided_assertion():
    assert "NEVER calculate" in SYSTEM
    assert "NEVER state what a rule says from memory" in SYSTEM
    assert "citation_returned" in SYSTEM
    assert "figures_present" in SYSTEM
    assert "unknown" in SYSTEM


# -- caps inside the loop (6.13) -----------------------------------------


def test_a_rate_limited_request_never_reaches_a_model(res):
    """
    The point of a spend cap is to not spend, so it is checked before the
    first model call.
    """
    from agent.budget import Budget

    budget = Budget(max_requests=1, window_seconds=60)
    budget.check_rate()
    script = Script(router=routing("data"), intent=planning(), answers=["should not be reached"])
    verdict = answer(script, question="q", res=res, budget=budget)
    assert verdict.over_budget is not None
    assert "rate limit" in verdict.over_budget
    assert script.answer_calls == 0
    assert verdict.tool_calls == []


def test_a_capped_request_returns_a_verdict_rather_than_raising(res):
    """
    A caller should get the same shape back whatever happened, and the reason
    should reach the user rather than becoming a 500.
    """
    from agent.budget import Budget

    budget = Budget(max_input_tokens=10)
    budget.record("m", Usage(input_tokens=100))
    verdict = answer(
        Script(router=routing("data"), intent=planning(), answers=["x"]),
        question="q",
        res=res,
        budget=budget,
    )
    assert verdict.over_budget is not None
    assert "cannot take that request" in verdict.text
    assert verdict.supported, "a capped request is accounted for, not an unexplained blank"
    assert "Refused by a cap" in verdict.render()


def test_a_request_records_what_it_cost(res):
    from agent.budget import Budget

    budget = Budget()
    script = Script(
        router=routing("rules"),
        intent=planning("Trade Rules"),
        answers=[[("fetch_provision", {"citation": "Art. VII §8"})], "The trade rules say..."],
    )
    verdict = answer(script, question="q", res=res, budget=budget)
    assert verdict.cost is not None
    assert verdict.cost.model_calls >= 3
    assert verdict.cost.tool_calls == 1
    assert verdict.cost.trace_units == verdict.trace.units > 0
    assert "Cost:" in verdict.render()


def test_no_budget_means_no_cost_recorded_rather_than_a_zero(res):
    verdict = answer(
        Script(router=routing("rules"), intent=planning(), answers=["x"]),
        question="q",
        res=res,
    )
    assert verdict.cost is None


def test_a_refused_question_still_records_its_cost(res):
    """
    The router call was made and the tokens were spent; reporting nothing would
    make refusals look free.
    """
    from agent.budget import Budget

    budget = Budget()
    verdict = answer(
        Script(router=routing("refused", basis="opinion"), intent=planning(), answers=[]),
        question="should they?",
        res=res,
        budget=budget,
    )
    assert verdict.refused
    assert verdict.cost is not None
    assert verdict.cost.model_calls == 1


# -- the trace the loop builds (6.10) ------------------------------------


def test_every_answer_carries_a_trace_even_with_no_vendor(res):
    """
    Built always; exporting is the caller's choice. A trace that only exists
    when a key is configured is a trace you cannot test.
    """
    from agent.trace import Kind

    script = Script(
        router=routing("rules"),
        intent=planning("Trade Rules"),
        answers=[[("fetch_provision", {"citation": "Art. VII §8"})], "The rules say..."],
    )
    verdict = answer(script, question="q", res=res, session="sess-1")
    assert verdict.trace is not None
    assert verdict.trace.session == "sess-1"
    assert verdict.trace.root is not None
    assert verdict.trace.root.kind is Kind.AGENT


def test_the_root_carries_the_question_and_the_answer(res):
    """
    The trace list shows the root's input and output, so those are what a
    reviewer reads first -- not a JSON blob of arguments.
    """
    verdict = answer(
        Script(router=routing("rules"), intent=planning(), answers=["Here is the answer."]),
        question="What is the Standard Traded Player Exception?",
        res=res,
    )
    assert verdict.trace is not None and verdict.trace.root is not None
    assert verdict.trace.root.input == "What is the Standard Traded Player Exception?"
    assert verdict.trace.root.output == "Here is the answer."


def test_a_tool_is_a_sibling_of_the_generation_that_requested_it(res):
    """
    Not a child of the generation, and not dangling at the trace root. The
    tree has to show which step each action belongs to.
    """
    from agent.trace import Kind

    verdict = answer(
        Script(
            router=routing("rules"),
            intent=planning(),
            answers=[[("fetch_provision", {"citation": "Art. VII §8"})], "x"],
        ),
        question="q",
        res=res,
    )
    assert verdict.trace is not None and verdict.trace.root is not None
    kinds = [c.kind for c in verdict.trace.root.children]
    assert Kind.GENERATION in kinds
    assert Kind.RETRIEVER in kinds
    for child in verdict.trace.root.children:
        assert child.children == [], "nothing nests under a generation or a tool"


def test_spans_are_named_for_the_step_not_the_model_or_the_role(res):
    """
    Names behave like an API: evaluators and dashboards target them, so they
    are verb-first, stable, and never carry the model.
    """
    verdict = answer(
        Script(
            router=routing("rules"),
            intent=planning(),
            answers=[[("fetch_provision", {"citation": "Art. VII §8"})], "x"],
        ),
        question="q",
        res=res,
    )
    assert verdict.trace is not None and verdict.trace.root is not None
    names = [c.name for c in verdict.trace.root.children]
    assert "classify-question" in names
    assert "select-provisions" in names
    assert "generate-answer" in names
    assert "fetch-provision" in names
    assert not any("stub" in n or "claude" in n for n in names)


def test_a_generation_records_the_model_and_token_usage(res):
    from agent.trace import Kind

    verdict = answer(
        Script(router=routing("rules"), intent=planning(), answers=["done"]),
        question="q",
        res=res,
    )
    assert verdict.trace is not None and verdict.trace.root is not None
    span = next(c for c in verdict.trace.root.children if c.kind is Kind.GENERATION)
    assert span.model == "stub"
    assert "input" in span.usage
    assert "cache_read_input_tokens" in span.usage


def test_the_system_prompt_is_clipped_rather_than_repeated_in_full(res):
    """
    D4 asks for the system prompt in the trace. The intent role's carries 612
    provision names -- about 16,000 characters -- and repeating it on every
    span would bury the conversation and cost money to store.
    """
    verdict = answer(
        Script(router=routing("rules"), intent=planning(), answers=["done"]),
        question="q",
        res=res,
    )
    assert verdict.trace is not None and verdict.trace.root is not None
    for child in verdict.trace.root.children:
        if not child.input or not isinstance(child.input, list):
            continue
        system = child.input[0]
        assert system["role"] == "system"
        assert len(system["content"]) < 1_000, "clipped, not verbatim"


def test_a_tool_span_summarises_rather_than_dumping_the_whole_result(res):
    """
    A fetch_provision result carries several thousand characters of provision
    text; a trace full of those is unreadable. The citation and the shape are
    what tell you whether the step did its job.
    """
    from agent.trace import Kind

    verdict = answer(
        Script(
            router=routing("rules"),
            intent=planning(),
            answers=[[("fetch_provision", {"citation": "Art. VII §6(j)(1)"})], "x"],
        ),
        question="q",
        res=res,
    )
    assert verdict.trace is not None and verdict.trace.root is not None
    span = next(c for c in verdict.trace.root.children if c.kind is Kind.RETRIEVER)
    assert span.output["citation_returned"] == "Art. VII §6(j)(1)"
    assert span.metadata["ok"] is True
    assert len(str(span.output)) < 1_000


def test_a_refusal_is_traced_as_an_event_with_its_basis(res):
    from agent.trace import Kind

    verdict = answer(
        Script(router=routing("refused", basis="historical"), intent=planning(), answers=[]),
        question="what was the cap in 2019?",
        res=res,
    )
    assert verdict.trace is not None and verdict.trace.root is not None
    event = next(c for c in verdict.trace.root.children if c.kind is Kind.EVENT)
    assert event.name == "refuse-question"
    assert event.metadata["basis"] == "historical"
    assert verdict.trace.scores["refused"] == 1


def test_judgements_become_scores_and_routing_becomes_tags(res):
    """
    Tags are immutable and set at creation, so they carry what is structural.
    Whether the answer was supported is only known afterwards, so it is a score.
    """
    verdict = answer(
        Script(
            router=routing("rules"),
            intent=planning("Trade Rules"),
            answers=[[("fetch_provision", {"citation": "Art. VII §8"})], "x"],
        ),
        question="q",
        res=res,
    )
    assert verdict.trace is not None
    assert verdict.trace.tags == ["rules"]
    assert verdict.trace.scores["supported"] == 1
    assert verdict.trace.scores["trustworthy"] == int(verdict.trustworthy)


def test_the_environment_is_recorded_so_test_runs_are_separable(res):
    verdict = answer(
        Script(router=routing("rules"), intent=planning(), answers=["x"]),
        question="q",
        res=res,
        environment="staging",
    )
    assert verdict.trace is not None
    assert verdict.trace.environment == "staging"
