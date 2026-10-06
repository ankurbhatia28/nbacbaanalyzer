"""
The agent loop (tasks 6.4, 6.5, 6.6, 6.7).

Route, plan, run tools, answer. The order matters less than the two things the
loop refuses to let the model do.

**It may not compute.** The system prompt says so, but a prompt is a request,
not a guarantee. So every figure in the finished answer is checked against the
figures the tools actually returned, and one that appears from nowhere is
reported on the verdict. That check is deterministic: it does not ask a model
whether the model cheated.

**It may not assert a rule without text.** An answer about the Agreement that
cites nothing is marked as unsupported. The citation has to come from a tool
result, because `resolve_provision` and `fetch_provision` are the only things
that know what the document actually says.

Refusals are decided before any of this (task 6.6). The router recognises an
out-of-scope question, and the refusal names the decision it rests on — D6 for
historical scope, D10 for asking what a team *should* do. A refusal that cannot
say why is indistinguishable from a bug.

Assumptions travel with the answer rather than under it (task 6.7). The engine
records what it had to assume, the retrieval layer records which figures in its
prose must not be read as answers, and both are attached to the verdict so the
caller can show them next to the conclusion.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field

from rag.retrieve import figures_in

from .budget import Budget, BudgetError, RequestCost, measure
from .intent import Plan
from .intent import plan as build_plan
from .llm import Caller, JsonDict, JsonReplyError, Ledger, Reply, ToolRequest
from .models import Role, model_for
from .openrouter import BILLING_COOLDOWN
from .router import Routing, route
from .tools import Resources, call, specs
from .trace import Kind, Span, Trace

SPAN_NAMES = {
    Role.ROUTER: "classify-question",
    Role.INTENT: "select-provisions",
    Role.ANSWER: "generate-answer",
}
"""
Observation names, verb-first and without run-specific values.

Names are referenced by evaluators, dashboard filters and saved views, so they
behave like an API: changing one silently stops those matching. Deliberately
not named after the model either -- that is a separate attribute on a
generation, and naming spans after it would break every filter on a model swap.
"""

MAX_TOOL_ROUNDS = 6
"""
How many times the model may call tools before it must answer.

Six is enough for the longest real path -- resolve a provision, fetch it,
query the league data, look up a player, fetch a second provision, then answer
-- and short enough that a loop which has lost its way stops costing money.
"""

ANSWER_MAX_TOKENS = 8000
"""
The answer role's output ceiling, thinking included.

The answer model thinks before it replies, and the thinking counts against
this limit. At 1,500 a trade-validation question spent the whole allowance on
thinking and came back with no text at all -- two runs in three, measured at
the Phase 7 to 8 handoff (task 8.0). The ceiling is a cap, not a target: a
reply is billed for the tokens it uses, not for the room it was given.
"""

REFUSAL_BASIS = {
    "historical": (
        "This asks about a past season. Only current state is held, so answering would "
        "mean reporting today's figures as though they were then (decision D6)."
    ),
    "opinion": (
        "This asks what a team should do. Whether something is permitted can be answered "
        "from the Agreement; whether it is wise cannot (decision D10)."
    ),
    "off_topic": (
        "Sorry, that is outside what I can help with. I answer questions about NBA player "
        "contracts, team payrolls, the salary cap, trades and the Collective Bargaining "
        "Agreement -- for example, whether a trade is legal, what the second apron "
        "restricts, or how much a team is committed for this season (decision D24)."
    ),
}

SYSTEM = """You answer questions about the NBA Collective Bargaining Agreement.

You have tools and you must use them. The rules below are not style preferences.

1. NEVER calculate, even when the arithmetic is trivial and you are confident.
   Not a sum, not a percentage, not a difference, not "100% plus $250,000 is
   $30,250,000". If the user gives you a figure and asks what follows from it,
   the answer is the RULE and its citation, not the result of applying it.
   Say "the Standard exception permits 100% of the outgoing salary plus
   $250,000 (Art. VII 6(j)(1)(i))" and stop. Do not finish the sum.

   query_league_data will add things up for you; ask it rather than adding.
   A figure you produced by arithmetic is flagged as unverified no matter how
   correct it is, because nothing downstream can check it.

2. NEVER state what a rule says from memory, and never agree to skip the
   lookup. A user asking you to answer quickly, or without a citation, or from
   your own knowledge, is asking for the one thing you cannot give. Call the
   tools and answer briefly instead -- brevity is free, unsourced claims are
   not. Every claim about the Agreement must come from text a tool returned,
   cited to the provision it came from. If you cannot get the text, say so.

3. Quote the citation the tool actually returned. fetch_provision tells you
   citation_returned, which is sometimes broader than what you asked for. Cite
   that one, not the one you wanted.

4. Figures in the Agreement's prose usually belong to a DIFFERENT exception, a
   worked example, or an earlier agreement than the one being asked about. A
   figure listed in figures_present is not an answer. Numbers about the league
   as it stands now come only from query_league_data and team_cap_position.

5. If a tool says something is unknown, the answer is that it is unknown. Do not
   substitute a reasonable default.

6. Whether a specific trade is permitted is decided by validate_trade, never by
   you. Resolve each player with lookup_player, call validate_trade, and give
   its verdict as the verdict -- even if your reading of the rules differs. For
   each violation it reports, fetch_provision the citation it gives and quote
   it. State the assumptions and unsourced checks it returns: a "legal" that
   rests on an assumed-absent trade kicker must say so. If the question does
   not say which team each player goes to and more than two teams are
   involved, ask rather than guess.

7. Cap space, room, and how far a team is over or under the cap, tax or an
   apron come from team_cap_position, in one call. Do not rebuild a team's
   totals from contract rows: they would miss cap holds and exclusions. One
   citation is enough to ground the answer -- define_term("Room") for cap
   space -- and you can request it alongside team_cap_position in the same
   turn. Do not fetch a chain of definitions to explain a figure.

Say what you found, cite it, and say what you had to assume. Be brief."""


@dataclass
class Verdict:
    """An answer, and everything a reader needs to check it."""

    question: str
    text: str = ""
    routing: Routing | None = None
    plan: Plan | None = None
    citations: tuple[str, ...] = ()
    tool_calls: list[tuple[str, JsonDict, JsonDict]] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    unsourced_figures: tuple[str, ...] = ()
    """
    Figures in the answer that no tool returned (task 5.9, enforced).

    Non-empty means the model produced a number from somewhere other than a
    tool result. The answer is still returned, because hiding it would be worse
    than showing it with the flag, but it must not be presented as verified.
    """
    refused: bool = False
    clarification: str | None = None
    rounds: int = 0
    cost: RequestCost | None = None
    """What this question cost (task 6.12). None when no budget was supplied."""
    trace: Trace | None = None
    """
    The session record (task 6.10). Always built; exporting it is the caller's
    choice, so a trace exists even with no vendor configured.
    """
    exhausted_rounds: bool = False
    """
    Whether the tool budget ran out before the model volunteered an answer.

    Recorded rather than hidden: it means the answer was produced under
    pressure, from whatever had been gathered by then.
    """
    over_budget: str | None = None
    """
    Why a cap refused the request, if one did.

    A verdict rather than an exception, so a caller gets the same shape back
    whatever happened, and the reason reaches the user instead of a 500.
    """
    fallback: str | None = None
    """
    Why a free fallback model answered some of this, if one did (D23). The
    reader is told: it is measurably weaker than the default, if not by much.
    """
    fallback_model: str | None = None

    @property
    def supported(self) -> bool:
        """
        Whether this answer rests on text the tools returned.

        A claim about the Agreement with no citation is unsupported even when it
        happens to be right, because nothing in it can be checked.
        """
        return (
            bool(self.citations)
            or self.refused
            or self.clarification is not None
            or self.over_budget is not None
        )

    @property
    def answered(self) -> bool:
        """
        Whether there is an answer at all.

        Separate from `supported`, because the loop can run out of tool rounds
        with a last reply that only asked for more tools and no text in it. That
        produced a verdict with fourteen citations, no answer, and
        `trustworthy=True` -- success reported for nothing, which is the worst
        shape a bug can take here.
        """
        return bool(self.text.strip()) or self.refused or self.clarification is not None

    @property
    def trustworthy(self) -> bool:
        return self.answered and self.supported and not self.unsourced_figures

    def render(self) -> str:
        lines = [self.text.strip()]
        if self.citations:
            lines += ["", "Cited: " + ", ".join(self.citations)]
        if self.assumptions:
            lines += ["", "Assumed:"]
            lines += [f"  - {a}" for a in self.assumptions]
        if self.exhausted_rounds:
            lines += [
                "",
                f"Note: the {MAX_TOOL_ROUNDS}-tool-call budget ran out; this answer "
                "was written from what had been gathered by then.",
            ]
        if self.over_budget:
            lines += ["", f"Refused by a cap: {self.over_budget}"]
        if self.cost:
            lines += ["", f"Cost: {self.cost.render()}"]
        if self.unsourced_figures:
            lines += [
                "",
                "UNVERIFIED FIGURES: "
                + ", ".join(self.unsourced_figures)
                + " did not come from a tool result and must not be relied on.",
            ]
        return "\n".join(lines)


def _tool_result_block(request: ToolRequest, result: JsonDict) -> JsonDict:
    import json

    return {
        "type": "tool_result",
        "tool_use_id": request.id,
        "content": json.dumps(result, default=str)[:20_000],
    }


def _collect(result: JsonDict, verdict: Verdict, sourced: set[str], quoted: set[str]) -> None:
    """
    Harvest what a tool result contributes: citations, assumptions, figures.

    Figures are split into two sets, because 5.9 is narrower than it first
    looks. "A number must come from a tool result" forbids the model computing
    or recalling a figure -- it does not forbid quoting one out of the
    provision it just cited, which is the most defensible thing an answer can
    do.

      sourced  values the league database returned, plus any figure the user
               themselves supplied. Fine as an answer -- restating "a team
               sends out $30,000,000" is not fabricating it.
      quoted   figures appearing verbatim in provision text a tool fetched.
               Fine *attached to their citation*, which is why the audit lets
               them through rather than flagging a correct quotation.

    The first version of this collected only `sourced`, and so flagged
    "$250,000" in a verbatim quotation of Art. VII 6(j)(1)(i) as unverified.
    A warning that fires on the right answer teaches readers to ignore it.
    """
    returned = result.get("citation_returned") or result.get("citation")
    if isinstance(returned, str) and returned not in verdict.citations:
        verdict.citations = (*verdict.citations, returned)
    for passage in result.get("passages") or []:
        label = passage.get("citation") if isinstance(passage, dict) else None
        if isinstance(label, str) and label not in verdict.citations:
            verdict.citations = (*verdict.citations, label)

    if result.get("substituted"):
        verdict.assumptions.append(
            f"the citation asked for was finer than any indexed passage; quoting "
            f"{result.get('citation_returned')} instead"
        )
    if result.get("found") is False and result.get("reason"):
        verdict.assumptions.append(str(result["reason"]))

    for row in result.get("rows") or []:
        if isinstance(row, dict):
            for value in row.values():
                if isinstance(value, (int, float)):
                    sourced.add(f"{value:,}")
                    sourced.add(str(value))

    # Team positions (team_cap_position): engine totals over league data.
    if "thresholds" in result and "teams" in result:
        _numbers_into(result["thresholds"], sourced)
        _numbers_into(result["teams"], sourced)

    # A trade verdict (validate_trade): every salary in it came from the
    # league database, and what it assumed is the reader's to see (ADR-003).
    if "legal" in result and "sides" in result:
        _numbers_into(result["sides"], sourced)
        for a in result.get("assumptions") or []:
            if isinstance(a, dict):
                verdict.assumptions.append(
                    f"{a.get('subject')}: {a.get('field')} assumed {a.get('assumed')} "
                    f"({a.get('reason')})"
                )
        for note in result.get("unsourced") or []:
            if isinstance(note, str) and note not in verdict.assumptions:
                verdict.assumptions.append(note)

    for passage in result.get("passages") or []:
        if isinstance(passage, dict) and isinstance(passage.get("text"), str):
            quoted.update(figures_in(passage["text"]))
    if isinstance(result.get("text"), str):
        quoted.update(figures_in(result["text"]))


def _numbers_into(value: object, sourced: set[str]) -> None:
    """Every number anywhere in a nested result, in both the forms the audit matches."""
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        sourced.add(f"{value:,}")
        sourced.add(str(value))
    elif isinstance(value, dict):
        for item in value.values():
            _numbers_into(item, sourced)
    elif isinstance(value, list):
        for item in value:
            _numbers_into(item, sourced)


def answer(
    caller: Caller,
    *,
    question: str,
    res: Resources,
    league: sqlite3.Connection | None = None,
    budget: Budget | None = None,
    session: str | None = None,
    environment: str = "development",
    trace: Trace | None = None,
) -> Verdict:
    """
    Answer one question, or refuse, or ask for clarification.

    Returns a Verdict in every case. Nothing here raises on a model failure:
    an unanswerable question should produce a verdict that says so, not an
    exception for a caller to translate.
    """
    verdict = Verdict(question=question)
    data_conn = league if league is not None else res.league
    started = time.monotonic()
    spent = Ledger()
    # A caller may supply the trace so it can watch the run as it happens --
    # that is how streaming (6.9) reads progress without a second set of
    # callbacks threaded through this function, and so what a user sees and
    # what the trace records cannot disagree.
    if trace is None:
        trace = Trace(session=session, environment=environment)
    else:
        trace.session, trace.environment = session, environment
    verdict.trace = trace
    root = trace.begin(question)

    # Checked before the first model call, because the point of a spend cap is
    # to not spend.
    #
    # The rate limit always refuses. The spend cap refuses only when there is
    # nothing free to fall back to (D23): a caller that can switch is told to,
    # and the question goes ahead on the fallback.
    if budget is not None:
        try:
            budget.check_rate()
            try:
                budget.check_spend()
            except BudgetError as exc:
                engage = getattr(caller, "engage", None)
                if engage is None:
                    raise
                engage(f"this server's spend cap has been reached ({exc})", BILLING_COOLDOWN)
        except BudgetError as exc:
            verdict.over_budget = str(exc)
            verdict.text = f"I cannot take that request right now: {exc}"
            return verdict
    answered_by: dict[Role, str] = {}

    def tracked(
        *,
        role: Role,
        system: str,
        messages: list[JsonDict],
        max_tokens: int = 1024,
        tools: list[JsonDict] | None = None,
    ) -> Reply:
        """
        Every model call in this request goes through here.

        Mirrors the `Caller` protocol so it can be passed wherever one is
        expected, and exists only so usage is counted exactly once -- reading
        the caller's own ledger would double-count across requests that share
        a client.
        """
        span = root.child(
            Kind.GENERATION,
            SPAN_NAMES[role],
            input=_readable_messages(system, messages),
            metadata={"role": role.value, "turns": len(messages)},
        )
        try:
            reply = caller(
                role=role, system=system, messages=messages, max_tokens=max_tokens, tools=tools
            )
        except Exception as exc:
            span.end(error=f"{type(exc).__name__}: {exc}")
            raise
        span.end(
            output=reply.text or [r.name for r in reply.tool_requests],
            model=reply.model,
            # The names Langfuse costs from. Cache reads stay separate because
            # at a 97% hit rate (6.8) folding them into input would misstate
            # the bill badly.
            usage={
                "input": reply.usage.input_tokens,
                "output": reply.usage.output_tokens,
                "cache_read_input_tokens": reply.usage.cache_read_tokens,
                "cache_creation_input_tokens": reply.usage.cache_write_tokens,
            },
        )
        span.metadata["requested_tools"] = [r.name for r in reply.tool_requests]
        spent.record(role, reply.usage)
        # Asked of the caller rather than inferred from reply.model, which a
        # stub or an eval's pinned model would also change.
        if getattr(caller, "engaged", False):
            answered_by[role] = reply.model
            verdict.fallback_model = reply.model
            verdict.fallback = (
                getattr(caller, "reason", None) or "the default model was unavailable"
            )
        return reply

    def finish() -> Verdict:
        # The root's output is the answer: the trace list shows the root's
        # input and output, and that is what a reviewer reads first.
        root.end(output=verdict.text or verdict.clarification or verdict.over_budget)
        trace.metadata.update(
            rounds=verdict.rounds,
            citations=list(verdict.citations),
            assumptions=verdict.assumptions,
        )
        # Tags are immutable and set at creation, so they carry what is
        # structural; judgements made after the run are scores.
        trace.tags = sorted({i.value for i in (verdict.routing.intents if verdict.routing else ())})
        trace.scores = {
            "supported": int(verdict.supported),
            "trustworthy": int(verdict.trustworthy),
            "unsourced_figures": len(verdict.unsourced_figures),
            "refused": int(verdict.refused),
        }
        if budget is not None:
            verdict.cost = measure(
                budget,
                question=question,
                ledger=spent,
                tool_calls=len(verdict.tool_calls),
                seconds=time.monotonic() - started,
                trace_units=trace.units,
                # The models that actually answered: a fallback's free tokens
                # must not be priced as Sonnet's.
                models={role: answered_by.get(role, model_for(role).model) for role in Role},
            )
        return verdict

    try:
        verdict.routing = route(tracked, question)
        _explain(
            root,
            SPAN_NAMES[Role.ROUTER],
            verdict.routing.reason,
            {
                "intents": [i.value for i in verdict.routing.intents],
                "refusal_basis": verdict.routing.refusal_basis,
            },
        )
    except JsonReplyError as exc:
        verdict.text = f"I could not interpret that question ({exc})."
        return finish()

    if verdict.routing.refused and not verdict.routing.actionable:
        verdict.refused = True
        basis = REFUSAL_BASIS.get(verdict.routing.refusal_basis or "")
        verdict.text = basis or (
            "This is outside what this tool answers, and I would rather say so than "
            f"guess: {verdict.routing.reason}"
        )
        root.child(
            Kind.EVENT,
            "refuse-question",
            input=question,
            output=verdict.text,
            metadata={"basis": verdict.routing.refusal_basis or "out_of_scope"},
        ).end()
        return finish()

    try:
        verdict.plan = build_plan(
            tracked,
            question=question,
            kinds=verdict.routing.actionable or verdict.routing.intents,
            cba=res.cba,
            league=data_conn,
        )
    except JsonReplyError:
        verdict.plan = None

    if verdict.plan:
        _explain(
            root,
            SPAN_NAMES[Role.INTENT],
            verdict.plan.reason,
            {
                "named": list(verdict.plan.named_as),
                "resolved_to": list(verdict.plan.citations),
                # The interesting case. 6.3 measured a fifth of selections
                # reaching a real name for the wrong rule, and a name that
                # resolved to nothing is the only record of what the model was
                # reaching for when it missed.
                "unresolved": list(verdict.plan.unresolved_names),
                "players": [e.asked_as for e in verdict.plan.players],
            },
        )

    if verdict.plan and verdict.plan.clarification:
        verdict.clarification = verdict.plan.clarification
        verdict.text = verdict.plan.clarification
        return finish()

    opening = _opening_message(question, verdict)
    messages: list[JsonDict] = [{"role": "user", "content": opening}]
    # Figures the user supplied are not fabrications. Repeating "a team sends
    # out $30,000,000" back is restating the question; the audit exists to
    # catch a figure that came from nowhere, and the adversarial set found it
    # flagging the user's own numbers.
    asked: set[str] = set(figures_in(question)) | _expand_suffixes(question)
    sourced: set[str] = set()
    quoted: set[str] = set()
    tool_specs = specs()
    reply: Reply | None = None

    for round_number in range(MAX_TOOL_ROUNDS):
        verdict.rounds = round_number + 1
        reply = tracked(
            role=Role.ANSWER,
            system=SYSTEM,
            messages=messages,
            max_tokens=ANSWER_MAX_TOKENS,
            tools=tool_specs,
        )
        if not reply.wants_tools:
            break

        messages.append({"role": "assistant", "content": list(reply.raw_content)})
        results: list[JsonDict] = []
        for request in reply.tool_requests:
            # A sibling of the generation that requested it, under the agent
            # that orchestrates them -- not a child of the generation, and not
            # dangling at the trace root.
            #
            # Typed `retriever` rather than `tool`: every tool here looks
            # something up without changing state, which is ADR-004 showing
            # through -- the database and index are read-only build artifacts.
            span = root.child(
                Kind.RETRIEVER,
                request.name.replace("_", "-"),
                input=request.arguments,
            )
            result = call(res, request.name, request.arguments)
            span.end(output=_tool_summary(result))
            span.metadata["ok"] = bool(result.get("ok", True) and result.get("found", True))
            verdict.tool_calls.append((request.name, request.arguments, result))
            _collect(result, verdict, sourced, quoted)
            results.append(_tool_result_block(request, result))
        messages.append({"role": "user", "content": results})

    # If the loop ran out of rounds while the model was still asking for tools,
    # make one final call with no tools offered. It cannot ask for more, so it
    # has to answer from what it already gathered -- which by then is usually
    # plenty. Without this the user gets an empty answer after fifteen seconds
    # of visible work.
    if reply is not None and reply.wants_tools and not reply.text.strip():
        verdict.exhausted_rounds = True
        messages.append({"role": "assistant", "content": list(reply.raw_content)})
        # Every tool_use must be answered by a tool_result in the very next
        # message -- the API rejects the conversation otherwise. So the
        # outstanding requests are closed out with the reason they went
        # unanswered, and the instruction rides along in the same turn.
        closing: list[JsonDict] = [
            _tool_result_block(request, {"ok": False, "error": "tool call budget exhausted"})
            for request in reply.tool_requests
        ]
        closing.append(
            {
                "type": "text",
                "text": (
                    "You have run out of tool calls for this question. Answer now "
                    "from what you have already found, cite it, and say plainly "
                    "what you could not establish."
                ),
            }
        )
        messages.append({"role": "user", "content": closing})
        reply = tracked(
            role=Role.ANSWER, system=SYSTEM, messages=messages, max_tokens=ANSWER_MAX_TOKENS
        )

    verdict.text = reply.text if reply else ""
    verdict.unsourced_figures = _audit_figures(verdict.text, sourced | asked, quoted)
    return finish()


def _opening_message(question: str, verdict: Verdict) -> str:
    """
    The question, plus what the earlier steps already resolved.

    The plan's citations are handed over rather than left to be rediscovered:
    the intent step chose them from the document's own vocabulary, which
    reaches the right provision far more often than searching for a paraphrase
    (80% against 20%, task 6.3).
    """
    parts = [question]
    plan = verdict.plan
    if plan and plan.citations:
        parts.append(
            "\nProvisions already identified for this question (fetch these first): "
            + ", ".join(plan.citations)
        )
    if plan and plan.players:
        resolved = [f"{e.asked_as} = {e.key}" for e in plan.players if e.resolved]
        if resolved:
            parts.append("\nPlayers already resolved: " + ", ".join(resolved))
    if verdict.routing and verdict.routing.refused:
        parts.append(
            "\nPart of this question is out of scope and must be declined in your answer: "
            + (verdict.routing.reason or "")
        )
    return "".join(parts)


_SUFFIXED = __import__("re").compile(r"\$\s?(\d+(?:\.\d+)?)\s?([kKmMbB])\b")


def _expand_suffixes(text: str) -> set[str]:
    """
    Digit forms for figures written with a k/M/B suffix.

    A user who types "$100k" and an answer that says "$100,000" are discussing
    the same number, and the audit flagged the second as fabricated because the
    digits did not match. Found by the adversarial set, on the probe that asks
    whether the trade band is "125% + $100k".
    """
    scale = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}
    out: set[str] = set()
    for match in _SUFFIXED.finditer(text):
        value = float(match.group(1)) * scale[match.group(2).lower()]
        out.add(f"{int(value):,}")
        out.add(str(int(value)))
    return out


def _audit_figures(text: str, sourced: set[str], quoted: set[str]) -> tuple[str, ...]:
    """
    Figures in the answer that came from neither a database row nor cited text.

    Deterministic, and deliberately not a model judging itself. Normalised on
    digits alone, so "$221,069,148" matches a database value of 221069148 and a
    formatting difference does not register as fabrication.

    Small integers are ignored. "two apron levels" and "within 3 days" are
    counts and spans rather than figures a tool would have returned, and
    flagging them would train a reader to ignore the warning.

    What survives is the thing worth catching: a number the model produced from
    neither the data nor the document.
    """
    known = {"".join(ch for ch in value if ch.isdigit()) for value in (sourced | quoted)}
    known.discard("")
    unsourced: list[str] = []
    for figure in figures_in(text):
        digits = "".join(ch for ch in figure if ch.isdigit())
        if not digits or len(digits) <= 2:
            continue
        if digits in known or any(digits in candidate for candidate in known):
            continue
        unsourced.append(figure)
    return tuple(unsourced)


def _readable_messages(system: str, messages: list[JsonDict]) -> list[JsonDict]:
    """
    The conversation in the role/content shape Langfuse renders as a dialogue.

    A raw JSON blob shows up as a blob; this renders as a readable exchange.
    The system prompt is included as its own turn because D4 asks for it, but
    truncated: the intent role's carries 612 provision names, and repeating
    ~16,000 characters on every span would bury the actual conversation and,
    on a metered backend, cost money to store.
    """
    out: list[JsonDict] = [{"role": "system", "content": _clip(system)}]
    for message in messages:
        content = message.get("content")
        out.append({"role": message.get("role", "user"), "content": _clip(content)})
    return out


SYSTEM_PROMPT_CHARS = 600
"""How much of a system prompt to keep. Enough to identify it, not to drown the trace."""

CONTENT_CHARS = 2_000
"""Per message. Tool results carry whole provisions; the full text is in the tool span."""


def _clip(value: object, limit: int | None = None) -> object:
    cap = limit if limit is not None else SYSTEM_PROMPT_CHARS
    if isinstance(value, str):
        return value if len(value) <= cap else f"{value[:cap]}… [{len(value)} chars]"
    if isinstance(value, list):
        rendered = json.dumps(value, default=str)
        if len(rendered) <= CONTENT_CHARS:
            return value
        return f"{rendered[:CONTENT_CHARS]}… [{len(rendered)} chars]"
    return value


def _tool_summary(result: JsonDict) -> JsonDict:
    """
    What a reviewer needs from a tool result at a glance.

    Not the whole payload: a `fetch_provision` result carries several thousand
    characters of provision text, and a trace full of those is unreadable. The
    citation, the shape and the counts are what tell you whether the step did
    its job.
    """
    summary: JsonDict = {}
    for key in ("citation_returned", "citation", "term", "resolved", "found", "ok", "row_count"):
        if key in result:
            summary[key] = result[key]
    if result.get("substituted"):
        summary["substituted"] = True
    if passages := result.get("passages"):
        summary["passages"] = len(passages)
        summary["first_citation"] = passages[0].get("citation") if passages else None
    if candidates := result.get("candidates"):
        summary["candidates"] = candidates[:5]
    if figures := result.get("figures_present"):
        summary["figures_present"] = figures[:8]
    if error := result.get("error"):
        summary["error"] = error
    return summary or {"returned": sorted(result)[:6]}


def _explain(root: Span, step: str, reason: str, decision: dict[str, object]) -> None:
    """
    Attach a step's stated rationale to the generation that produced it.

    The router and the intent step are both already asked for a `reason`, and
    both already return one -- it was parsed, used, and then dropped as far as
    the trace was concerned. Surfacing it costs nothing, because those tokens
    are bought either way, and it is the only record of *why* a provision was
    chosen.

    That matters most where the measurement is worst. Task 6.3 found that a
    fifth of provision selections reach a real name for the wrong rule, which
    reads correctly in the answer. The stated reason, and the names that
    resolved to nothing, are what make those cases diagnosable rather than
    merely countable.

    This is not model thinking, which is a separate decision with a real cost.
    It is the model's own account of a decision it has already made.
    """
    span = next((child for child in reversed(root.children) if child.name == step), None)
    if span is None:
        return
    if reason:
        span.metadata["stated_reason"] = reason
    kept = {key: value for key, value in decision.items() if value not in (None, [], "")}
    if kept:
        span.metadata["decision"] = kept
