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

import sqlite3
from dataclasses import dataclass, field

from rag.retrieve import figures_in

from .intent import Plan
from .intent import plan as build_plan
from .llm import Caller, JsonDict, JsonReplyError, Reply, ToolRequest
from .models import Role
from .router import Routing, route
from .tools import Resources, call, specs

MAX_TOOL_ROUNDS = 6
"""
How many times the model may call tools before it must answer.

Six is enough for the longest real path -- resolve a provision, fetch it,
query the league data, look up a player, fetch a second provision, then answer
-- and short enough that a loop which has lost its way stops costing money.
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
}

SYSTEM = """You answer questions about the NBA Collective Bargaining Agreement.

You have tools and you must use them. The rules below are not style preferences.

1. NEVER calculate. Not a sum, not a percentage, not a difference, not a
   comparison of two figures. If a question needs arithmetic, the tool that owns
   that arithmetic performs it. query_league_data will sum for you; ask it.

2. NEVER state what a rule says from memory. Every claim about the Agreement
   must come from text a tool returned, and you must cite the provision it came
   from. If you cannot get the text, say you could not find it.

3. Quote the citation the tool actually returned. fetch_provision tells you
   citation_returned, which is sometimes broader than what you asked for. Cite
   that one, not the one you wanted.

4. Figures in the Agreement's prose usually belong to a DIFFERENT exception, a
   worked example, or an earlier agreement than the one being asked about. A
   figure listed in figures_present is not an answer. Numbers about the league
   as it stands now come only from query_league_data.

5. If a tool says something is unknown, the answer is that it is unknown. Do not
   substitute a reasonable default.

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

    @property
    def supported(self) -> bool:
        """
        Whether this answer rests on text the tools returned.

        A claim about the Agreement with no citation is unsupported even when it
        happens to be right, because nothing in it can be checked.
        """
        return bool(self.citations) or self.refused or self.clarification is not None

    @property
    def trustworthy(self) -> bool:
        return self.supported and not self.unsourced_figures

    def render(self) -> str:
        lines = [self.text.strip()]
        if self.citations:
            lines += ["", "Cited: " + ", ".join(self.citations)]
        if self.assumptions:
            lines += ["", "Assumed:"]
            lines += [f"  - {a}" for a in self.assumptions]
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

      sourced  values the league database returned. Fine as an answer.
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

    for passage in result.get("passages") or []:
        if isinstance(passage, dict) and isinstance(passage.get("text"), str):
            quoted.update(figures_in(passage["text"]))
    if isinstance(result.get("text"), str):
        quoted.update(figures_in(result["text"]))


def answer(
    caller: Caller,
    *,
    question: str,
    res: Resources,
    league: sqlite3.Connection | None = None,
) -> Verdict:
    """
    Answer one question, or refuse, or ask for clarification.

    Returns a Verdict in every case. Nothing here raises on a model failure:
    an unanswerable question should produce a verdict that says so, not an
    exception for a caller to translate.
    """
    verdict = Verdict(question=question)
    data_conn = league if league is not None else res.league

    try:
        verdict.routing = route(caller, question)
    except JsonReplyError as exc:
        verdict.text = f"I could not interpret that question ({exc})."
        return verdict

    if verdict.routing.refused and not verdict.routing.actionable:
        verdict.refused = True
        basis = REFUSAL_BASIS.get(verdict.routing.refusal_basis or "")
        verdict.text = basis or (
            "This is outside what this tool answers, and I would rather say so than "
            f"guess: {verdict.routing.reason}"
        )
        return verdict

    try:
        verdict.plan = build_plan(
            caller,
            question=question,
            kinds=verdict.routing.actionable or verdict.routing.intents,
            cba=res.cba,
            league=data_conn,
        )
    except JsonReplyError:
        verdict.plan = None

    if verdict.plan and verdict.plan.clarification:
        verdict.clarification = verdict.plan.clarification
        verdict.text = verdict.plan.clarification
        return verdict

    opening = _opening_message(question, verdict)
    messages: list[JsonDict] = [{"role": "user", "content": opening}]
    sourced: set[str] = set()
    quoted: set[str] = set()
    tool_specs = specs()
    reply: Reply | None = None

    for round_number in range(MAX_TOOL_ROUNDS):
        verdict.rounds = round_number + 1
        reply = caller(
            role=Role.ANSWER,
            system=SYSTEM,
            messages=messages,
            max_tokens=1500,
            tools=tool_specs,
        )
        if not reply.wants_tools:
            break

        messages.append({"role": "assistant", "content": list(reply.raw_content)})
        results: list[JsonDict] = []
        for request in reply.tool_requests:
            result = call(res, request.name, request.arguments)
            verdict.tool_calls.append((request.name, request.arguments, result))
            _collect(result, verdict, sourced, quoted)
            results.append(_tool_result_block(request, result))
        messages.append({"role": "user", "content": results})

    verdict.text = reply.text if reply else ""
    verdict.unsourced_figures = _audit_figures(verdict.text, sourced, quoted)
    return verdict


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
