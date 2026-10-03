"""
The answer card: what the interface shows for one question (tasks 7.2, 7.3, 7.6).

A `Verdict` is everything the loop knows. A card is what a reader needs to
*check* it, and the two are not the same shape: the verdict holds the raw tool
results the quotes and figures came from, and the card holds the quotes and
figures themselves.

Built here rather than in the web app for two reasons. **It is the contract**:
the API serialises a card and the frontend renders one, so this is the single
definition of what an answer looks like on the wire, tested in Python before
any TypeScript depends on it. And **it is deterministic**: every field comes
from a tool result or from the verdict's own audit. Nothing in a card is
written by a model except `text`, and `verified` says whether the audit passed
on that text.

What it carries, and why each is here:

  quotes      Verbatim provision text, from the tools that read the document.
              The card's promise is that a reader can see the words a rule
              rests on, not a paraphrase of them.
  figures     Every league-data query, with its SQL and parameters (7.3) and
              where each row came from and when (7.6). A number whose
              derivation cannot be inspected is a number you cannot check.
  warnings    Everything that should stop a reader trusting the answer as
              written. Separate from assumptions: an assumption is a stated
              premise, a warning is a defect.
  dataset     When the dataset was built and when each source was read. Shown
              on every answer, because a public app implies currency.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from nbadata.query import Snapshot
from rag.retrieve import figures_in

from .answer import MAX_TOOL_ROUNDS, REFUSAL_BASIS, Verdict
from .llm import JsonDict

SCHEMA_VERSION = 1
"""
Bumped on any change a renderer would notice. The frontend checks it, so a
card it does not understand fails loudly instead of rendering half its fields.
"""

QUOTING_TOOLS = ("fetch_provision", "search_cba", "define_term")


class Status(StrEnum):
    ANSWERED = "answered"
    REFUSED = "refused"
    CLARIFICATION = "clarification"
    UNAVAILABLE = "unavailable"
    """A cap refused the request, or the run produced no answer at all."""


class WarningKind(StrEnum):
    UNSOURCED_FIGURES = "unsourced_figures"
    UNSUPPORTED = "unsupported"
    EXHAUSTED_ROUNDS = "exhausted_rounds"
    UNKNOWN_VALUES = "unknown_values"
    UNDATED_ROWS = "undated_rows"


@dataclass(frozen=True, slots=True)
class Quote:
    """Provision text exactly as a tool returned it."""

    citation: str
    text: str
    tool: str
    pdf_page: int | None = None
    printed_page: int | None = None
    cited_in_answer: bool = False
    """
    Whether the answer text names this citation. Lets a renderer lead with the
    passages the answer relies on and fold away the ones read on the way.
    """


@dataclass(frozen=True, slots=True)
class Figure:
    """One league-data query: what it asked, what it returned, and from where."""

    sql: str
    params: list[Any]
    columns: list[str]
    rows: list[dict[str, Any]]
    provenance: list[dict[str, Any]]
    in_answer: list[str] = field(default_factory=list)
    """
    Figures in the answer text that this query's rows supplied, as written in
    the answer. How a renderer attaches "show the query" to the right number.
    """


@dataclass(frozen=True, slots=True)
class Warning:
    kind: WarningKind
    message: str
    detail: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class AnswerCard:
    question: str
    status: Status
    verified: bool
    """
    The verdict's `trustworthy`: answered, cited, and every figure accounted
    for. A renderer must not present an unverified card as checked.
    """
    text: str
    citations: list[str]
    quotes: list[Quote]
    figures: list[Figure]
    assumptions: list[str]
    warnings: list[Warning]
    refusal_basis: str | None = None
    dataset: dict[str, Any] | None = None
    cost_usd: float | None = None
    seconds: float | None = None
    schema: int = SCHEMA_VERSION

    def to_json(self) -> JsonDict:
        return asdict(self)


def build(verdict: Verdict, dataset: Snapshot | None = None) -> AnswerCard:
    """Turn a verdict into the card a reader sees. Pure: no I/O, no model."""
    quotes = _quotes(verdict)
    figures = _figures(verdict)
    cost = verdict.cost
    return AnswerCard(
        question=verdict.question,
        status=_status(verdict),
        verified=verdict.trustworthy,
        text=verdict.text,
        citations=list(verdict.citations),
        quotes=quotes,
        figures=figures,
        assumptions=list(verdict.assumptions),
        warnings=_warnings(verdict, figures),
        refusal_basis=_refusal_basis(verdict),
        dataset=dataset.to_json() if dataset else None,
        cost_usd=cost.dollars if cost else None,
        seconds=round(cost.seconds, 2) if cost else None,
    )


# -- pieces ---------------------------------------------------------------


def _status(verdict: Verdict) -> Status:
    if verdict.over_budget or not verdict.answered:
        return Status.UNAVAILABLE
    if verdict.refused:
        return Status.REFUSED
    if verdict.clarification is not None:
        return Status.CLARIFICATION
    return Status.ANSWERED


def _refusal_basis(verdict: Verdict) -> str | None:
    """
    The decision a refusal rests on, in words. Carried for a partial refusal
    too -- a question that is half in scope gets an answer *and* a reason the
    other half was declined.
    """
    if verdict.routing is None or not verdict.routing.refused:
        return None
    basis = verdict.routing.refusal_basis or ""
    return REFUSAL_BASIS.get(basis) or verdict.routing.reason or None


def _normalised(citation: str) -> str:
    return "".join(citation.split()).lower()


def _quotes(verdict: Verdict) -> list[Quote]:
    answer = _normalised(verdict.text)
    seen: set[tuple[str, str]] = set()
    out: list[Quote] = []

    def add(citation: Any, text: Any, tool: str, pdf: Any = None, printed: Any = None) -> None:
        if not isinstance(citation, str) or not isinstance(text, str) or not text.strip():
            return
        key = (citation, text)
        if key in seen:
            return
        seen.add(key)
        out.append(
            Quote(
                citation=citation,
                text=text,
                tool=tool,
                pdf_page=pdf if isinstance(pdf, int) else None,
                printed_page=printed if isinstance(printed, int) else None,
                cited_in_answer=bool(citation) and _normalised(citation) in answer,
            )
        )

    for name, _args, result in verdict.tool_calls:
        if name not in QUOTING_TOOLS:
            continue
        if name == "define_term" and result.get("found"):
            add(result.get("citation"), result.get("text"), name, result.get("pdf_page"))
            continue
        for passage in result.get("passages") or []:
            if not isinstance(passage, dict):
                continue
            # Context pulled in because a match referred to it is not evidence,
            # and showing it as a quote would imply the answer rests on it.
            if passage.get("is_evidence") is False:
                continue
            add(
                passage.get("citation"),
                passage.get("text"),
                name,
                passage.get("pdf_page"),
                passage.get("printed_page"),
            )
    # Stable: the passages the answer names first, otherwise in the order read.
    return sorted(out, key=lambda q: not q.cited_in_answer)


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def _figures(verdict: Verdict) -> list[Figure]:
    in_text = [(f, _digits(f)) for f in figures_in(verdict.text)]
    out: list[Figure] = []
    for name, _args, result in verdict.tool_calls:
        if name != "query_league_data" or not result.get("ok"):
            continue
        rows = [r for r in result.get("rows") or [] if isinstance(r, dict)]
        values = {
            _digits(str(v)) for row in rows for v in row.values() if isinstance(v, (int, float))
        }
        values.discard("")
        out.append(
            Figure(
                sql=str(result.get("sql", "")),
                params=list(result.get("params") or []),
                columns=list(result.get("columns") or []),
                rows=rows,
                provenance=list(result.get("provenance") or []),
                in_answer=[f for f, d in in_text if len(d) > 2 and d in values],
            )
        )
    return out


def _warnings(verdict: Verdict, figures: list[Figure]) -> list[Warning]:
    out: list[Warning] = []
    if verdict.unsourced_figures:
        out.append(
            Warning(
                WarningKind.UNSOURCED_FIGURES,
                "These figures did not come from a tool result and must not be relied on.",
                list(verdict.unsourced_figures),
            )
        )
    if verdict.answered and not verdict.supported:
        out.append(
            Warning(
                WarningKind.UNSUPPORTED,
                "This answer cites no provision, so nothing in it can be checked "
                "against the Agreement.",
            )
        )
    if verdict.exhausted_rounds:
        out.append(
            Warning(
                WarningKind.EXHAUSTED_ROUNDS,
                f"The {MAX_TOOL_ROUNDS}-tool-call budget ran out; this answer was "
                "written from what had been gathered by then.",
            )
        )

    # ADR-003: a value the data marks unknown must be visible as unknown on the
    # card, not left for a reader to spot in a table of rows.
    unknown = sorted(
        {
            column
            for figure in figures
            for row in figure.rows
            for column, value in row.items()
            if value == "unknown"
        }
    )
    if unknown:
        out.append(
            Warning(
                WarningKind.UNKNOWN_VALUES,
                "Some values are unknown in the source data. Unknown is not "
                "a default: read them as not known, not as the usual case.",
                unknown,
            )
        )

    undated = sorted(
        {
            str(p.get("source"))
            for figure in figures
            for p in figure.provenance
            if p.get("basis") == "undated"
        }
    )
    if undated:
        out.append(
            Warning(
                WarningKind.UNDATED_ROWS,
                "Some figures come from rows with no recorded date, so how current "
                "they are is unknown.",
                undated,
            )
        )
    return out
