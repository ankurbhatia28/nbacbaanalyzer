"""
The tools the model may call (task 6.2).

Every tool here is deterministic. Given the same arguments it returns the same
result, computed by the engine, the query layer or the retrieval index -- never
by the model. That is the whole point of ADR-001: the model decides *which
question is being asked* and *which provision to read*, and nothing else.

Two consequences shape the schemas.

**No tool accepts a number the model made up.** There is no
`check_salary_match(outgoing=47_000_000)` here, because a model that can pass a
figure can pass a wrong one and the error becomes invisible. Tools take
identifiers -- a team, a player, a citation -- and look the figures up.

**Schemas are generated where a closed set exists.** `query_league_data`
enumerates the catalog's entities and each one's fields, so a query naming a
field that does not exist is rejected before it runs rather than producing a
plausible number from the wrong column. `resolve_provision` is backed by the
document's own 670-name vocabulary (D14). A model cannot invent its way past
either.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from nbadata import sheet, state, trades
from nbadata.query import (
    ENTITIES,
    Agg,
    Filter,
    Op,
    Order,
    Projection,
    Query,
    QueryError,
    lookup_player,
)
from nbadata.query import run as run_query
from nbadata.state import MissingDataError
from rag import index as ix
from rag.retrieve import for_citation, retrieve

JsonDict = dict[str, Any]


@dataclass
class Resources:
    """
    What the tools read from.

    Both connections are read-only (ADR-004): the league database and the
    retrieval index are build artifacts, and a request cannot write to either.
    """

    league: sqlite3.Connection
    """The league database: contracts, holds, picks, ceilings."""
    cba: sqlite3.Connection
    """The retrieval index: provisions, definitions, cross-references."""
    base_season_cap: int
    """
    The 2023-24 cap, needed by the Expanded exception's growth factor.

    Passed in rather than looked up inside a handler so a missing figure fails
    at construction instead of halfway through answering a question.
    """


@dataclass(frozen=True, slots=True)
class Tool:
    """One callable tool, with the schema the model sees."""

    name: str
    description: str
    input_schema: JsonDict
    handler: Callable[[Resources, JsonDict], JsonDict]
    reads_cba_text: bool = False
    """
    Whether results contain document prose.

    Prose carries figures that belong to other provisions, prior CBAs or worked
    examples, so results from these tools are marked and the model is forbidden
    to answer a number out of them (task 5.9).
    """

    def spec(self) -> JsonDict:
        """The tool definition in the shape the Anthropic API expects."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


# -- schema generation ----------------------------------------------------


def _entity_field_schema() -> JsonDict:
    """
    One schema branch per entity, each listing only that entity's own fields.

    Generated from the catalog so a renamed column cannot leave a stale schema
    behind, and so the model is told the available fields rather than guessing.
    A single flat "field: string" would let a query name `cap_holds.salary`,
    which does not exist, and the failure would surface as an empty result
    rather than an error.
    """
    return {
        name: {
            "description": entity.description,
            "fields": {f.name: f.type.value for f in entity.fields},
        }
        for name, entity in ENTITIES.items()
    }


def _query_tool_schema() -> JsonDict:
    entities = _entity_field_schema()
    catalog = "\n".join(
        f"  {name}: {spec['description']}\n    fields: "
        + ", ".join(f"{f} ({t})" for f, t in spec["fields"].items())
        for name, spec in entities.items()
    )
    return {
        "type": "object",
        "properties": {
            "entity": {
                "type": "string",
                "enum": sorted(ENTITIES),
                "description": f"Which table to read. Available:\n{catalog}",
            },
            "select": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {
                            "type": "string",
                            "description": "A field of the chosen entity, or '*' with agg=count.",
                        },
                        "agg": {"type": "string", "enum": [a.value for a in Agg]},
                        "alias": {"type": "string"},
                    },
                    "required": ["field"],
                    "additionalProperties": False,
                },
            },
            "filters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string"},
                        "op": {"type": "string", "enum": [o.value for o in Op]},
                        "value": {"description": "Omit for is_null and not_null; a list for 'in'."},
                    },
                    "required": ["field", "op"],
                    "additionalProperties": False,
                },
            },
            "group_by": {"type": "array", "items": {"type": "string"}},
            "order_by": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string"},
                        "descending": {"type": "boolean"},
                    },
                    "required": ["field"],
                    "additionalProperties": False,
                },
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
        },
        "required": ["entity", "select"],
        "additionalProperties": False,
    }


# -- handlers -------------------------------------------------------------


def _resolve_provision(res: Resources, args: JsonDict) -> JsonDict:
    name = str(args.get("name", ""))
    resolved = ix.resolve_term(res.cba, name)
    if resolved is None:
        # A near miss is not offered as an answer. Candidates are returned so a
        # bounded retry has something real to pick from, but the tool does not
        # guess which one was meant.
        lowered = name.lower()
        words = [w for w in lowered.split() if len(w) > 3]
        candidates = [
            candidate
            for candidate in ix.vocabulary_names(res.cba)
            if any(word in candidate for word in words)
        ]
        return {
            "resolved": False,
            "reason": f"{name!r} is not a name this document uses.",
            "candidates": candidates[:15],
        }
    citation, kind = resolved
    return {"resolved": True, "citation": citation, "named_as": kind}


def _fetch_provision(res: Resources, args: JsonDict) -> JsonDict:
    citation = str(args.get("citation", ""))
    result = for_citation(res.cba, citation)
    if not result.passages:
        return {
            "found": False,
            "reason": f"{citation!r} is not a provision in this document.",
        }
    return {
        "found": True,
        "citation_requested": citation,
        "citation_returned": result.resolved_to or citation,
        "substituted": result.resolved_to is not None,
        "passages": [
            {
                "citation": p.label,
                "pdf_page": p.pdf_page,
                "printed_page": p.printed_page,
                "text": p.text,
            }
            for p in result.passages
        ],
        "defined_terms": [{"term": d.term, "citation": d.citation} for d in result.definitions],
        "figures_present": result.figures,
    }


def _search_cba(res: Resources, args: JsonDict) -> JsonDict:
    query = str(args.get("query", ""))
    limit = int(args.get("limit", 5))
    result = retrieve(res.cba, query, limit=min(limit, 10))
    return {
        "passages": [
            {
                "citation": p.label,
                "pdf_page": p.pdf_page,
                "printed_page": p.printed_page,
                "text": p.text,
                "why": p.why.value,
                "is_evidence": p.is_evidence,
            }
            for p in result.passages
        ],
        "defined_terms": [{"term": d.term, "citation": d.citation} for d in result.definitions],
        "figures_present": result.figures,
    }


def _define_term(res: Resources, args: JsonDict) -> JsonDict:
    term = str(args.get("term", ""))
    definition = ix.definition_for(res.cba, term)
    if definition is None:
        return {
            "found": False,
            "reason": f"{term!r} is not a term this Agreement defines.",
        }
    return {
        "found": True,
        "term": definition.term,
        "citation": definition.citation,
        "pdf_page": definition.pdf_page,
        "text": definition.body,
    }


def _query_league_data(res: Resources, args: JsonDict) -> JsonDict:
    try:
        query = Query(
            entity=str(args["entity"]),
            select=[
                Projection(
                    field=str(p["field"]),
                    agg=Agg(p["agg"]) if p.get("agg") else None,
                    alias=p.get("alias"),
                )
                for p in args.get("select", [])
            ],
            filters=[
                Filter(field=str(f["field"]), op=Op(f["op"]), value=f.get("value"))
                for f in args.get("filters", [])
            ],
            group_by=[str(g) for g in args.get("group_by", [])],
            order_by=[
                Order(field=str(o["field"]), descending=bool(o.get("descending")))
                for o in args.get("order_by", [])
            ],
            limit=int(args.get("limit", 100)),
        )
        result = run_query(res.league, query)
    except (QueryError, KeyError, ValueError) as exc:
        # The error carries what was allowed, so a bounded retry has something
        # to act on. A bare "invalid query" burns a turn and teaches nothing.
        return {"ok": False, "error": str(exc)}
    return {
        "ok": True,
        "columns": result.columns,
        "rows": result.rows,
        "row_count": result.row_count,
        "sql": result.sql,
        "params": result.params,
        # Which source each row came from and when (7.6). Returned to the model
        # as well as the UI, so an answer can say "as of" without guessing.
        "provenance": [o.to_json() for o in result.provenance],
    }


def _lookup_player(res: Resources, args: JsonDict) -> JsonDict:
    name = str(args.get("name", ""))
    matches = lookup_player(res.league, name)
    return {
        "candidates": [
            {
                "player_key": m.player_key,
                "display_name": m.display_name,
                "years_of_service": m.years_of_service,
                "exact": m.exact,
            }
            for m in matches
        ],
        "unambiguous": len(matches) == 1,
    }


def _validate_trade(res: Resources, args: JsonDict) -> JsonDict:
    """
    The engine's verdict on a proposed trade -- the same check the trade
    builder runs (7.4), so the chat and the builder cannot disagree.

    Takes players and teams, never a figure: the salaries are looked up. A
    trade that is not one (a player the team does not hold, a player moved
    twice) comes back as an error the model can report or correct.
    """
    moves = [
        trades.Move(
            str(m["player"]).strip().lower(),
            str(m["from_team"]).strip().upper(),
            str(m["to_team"]).strip().upper(),
        )
        for m in args.get("moves", [])
    ]
    try:
        verdict, sides, built = trades.check(res.league, moves, date.today())
    except (trades.TradeError, MissingDataError) as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, **trades.to_json(verdict, sides, built)}


def _team_cap_position(res: Resources, args: JsonDict) -> JsonDict:
    """
    Each team's totals against the four thresholds -- the cap sheet's own
    figures (7.5), so the chat and the cap sheet cannot disagree.

    Added because "which team has the most cap space?" was being answered by
    rebuilding team totals out of contract rows: it picked a season, summed
    salaries, forgot the cap holds, and spent the six-round budget before it
    had a number (12 tool calls, $0.10, no answer). The engine already
    computes the totals, holds included, for every team.
    """
    keys = [str(k).strip().upper() for k in args.get("teams") or []]
    if not keys:
        keys = [t.key for t in state.teams(res.league)]
    teams: list[JsonDict] = []
    thresholds: dict[str, int] = {}
    for key in keys:
        try:
            got = sheet.cap_sheet(res.league, key)
        except MissingDataError as exc:
            return {"ok": False, "error": str(exc)}
        thresholds = got.thresholds
        cap, apron = got.totals["cap"], got.totals["apron"]
        teams.append(
            {
                "team": got.team,
                "name": got.name,
                "status": got.status,
                "cap_salary": cap,
                "cap_holds": sum(line.cap for line in got.lines if line.kind == "hold"),
                "apron_salary": apron,
                "below_salary_cap": thresholds["salary_cap"] - cap,
                "below_tax_level": thresholds["tax_level"] - apron,
                "below_first_apron": thresholds["first_apron"] - apron,
                "below_second_apron": thresholds["second_apron"] - apron,
                "hard_cap": got.ceiling,
            }
        )
    teams.sort(key=lambda t: t["below_salary_cap"], reverse=True)
    return {
        "ok": True,
        "season": state.CURRENT_SEASON,
        "thresholds": thresholds,
        "teams": teams,
        "notes": [
            "Sorted by below_salary_cap, most room first. A negative value is how far "
            "over the threshold the team is.",
            "cap_salary includes cap holds, as Team Salary does for room; a team can "
            "remove a hold by renouncing the player, so its room may grow by up to "
            "cap_holds. apron_salary excludes most holds (Art. VII §2(e)(1)).",
            "The tax level and both aprons are measured on apron_salary, as the engine's "
            "status is.",
        ],
    }


HANDLERS: dict[str, Callable[[Resources, JsonDict], JsonDict]] = {
    "resolve_provision": _resolve_provision,
    "fetch_provision": _fetch_provision,
    "search_cba": _search_cba,
    "define_term": _define_term,
    "query_league_data": _query_league_data,
    "lookup_player": _lookup_player,
    "validate_trade": _validate_trade,
    "team_cap_position": _team_cap_position,
}


# -- the catalog ----------------------------------------------------------

TOOLS: tuple[Tool, ...] = (
    Tool(
        name="resolve_provision",
        description=(
            "Turn the name of a rule into its citation. This is the preferred way to "
            "reach a provision: the Agreement names its own rules, and those names "
            "resolve exactly. Use it when the question is about a named rule -- "
            "'Standard Traded Player Exception', 'Transaction Restrictions Table', "
            "'Over 38 Rule'. If the name is not one the document uses, the tool says so "
            "and offers the names that are closest; it does not guess."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": (
                        "The rule's name as the Agreement words it. Do not invent a name; "
                        "if unsure, try search_cba first and read the heading it returns."
                    ),
                }
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        handler=_resolve_provision,
    ),
    Tool(
        name="fetch_provision",
        description=(
            "Return the verbatim text of a provision by citation, with the defined terms "
            "it relies on. No search and no ranking: the citation determines the text. "
            "If the citation is finer than any indexed passage the tool returns the "
            "passage containing it and says so in citation_returned -- quote that, not "
            "what you asked for."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "citation": {
                    "type": "string",
                    "description": "For example 'Art. VII §6(j)(1)(i)' or 'Art. VII §8'.",
                }
            },
            "required": ["citation"],
            "additionalProperties": False,
        },
        handler=_fetch_provision,
        reads_cba_text=True,
    ),
    Tool(
        name="search_cba",
        description=(
            "Search the Agreement's text. Use this only when the question does not name "
            "a rule you can resolve -- search is measurably weaker than resolution "
            "(20% against 100% at reaching the right provision), so prefer "
            "resolve_provision whenever a name is available. Passages marked "
            "is_evidence=false were pulled in as context because a matching passage "
            "referred to them; they are not what matched."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        handler=_search_cba,
        reads_cba_text=True,
    ),
    Tool(
        name="define_term",
        description=(
            "The Agreement's definition of a term of art, with its citation. Article I "
            "fixes meanings that govern every other Article, so a provision read without "
            "them can be read wrongly. Capitalisation matters: the document capitalises a "
            "term where it carries its defined meaning."
        ),
        input_schema={
            "type": "object",
            "properties": {"term": {"type": "string"}},
            "required": ["term"],
            "additionalProperties": False,
        },
        handler=_define_term,
        reads_cba_text=True,
    ),
    Tool(
        name="query_league_data",
        description=(
            "Read the league database with a structured query. Salaries, contract years, "
            "options, cap holds, draft picks, hard-cap ceilings, trade exceptions, awards "
            "and the season cap figures. You choose the entity, fields and filters; the "
            "SQL is generated and returned with the result so the number can be checked. "
            "Never compute a total yourself -- ask for sum."
        ),
        input_schema=_query_tool_schema(),
        handler=_query_league_data,
    ),
    Tool(
        name="lookup_player",
        description=(
            "Resolve a player's name to the key the other tools use. Returns every "
            "candidate rather than a best guess; if unambiguous is false, ask the user "
            "which player they meant instead of choosing one."
        ),
        input_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        },
        handler=_lookup_player,
    ),
    Tool(
        name="validate_trade",
        description=(
            "Whether a specific proposed trade is permitted, decided by the rules engine "
            "against current payrolls. This is the only source of a trade verdict: never "
            "reach one yourself. Give each player's key (from lookup_player) and the teams "
            "it moves between, as team keys like DEN or BKN. Returns legal, each team's "
            "violations with the provision each one cites, the salaries involved, and what "
            "the verdict assumes because no source carries it -- report those assumptions."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "moves": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": trades.MAX_MOVES,
                    "items": {
                        "type": "object",
                        "properties": {
                            "player": {"type": "string", "description": "player key"},
                            "from_team": {"type": "string", "description": "team key"},
                            "to_team": {"type": "string", "description": "team key"},
                        },
                        "required": ["player", "from_team", "to_team"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["moves"],
            "additionalProperties": False,
        },
        handler=_validate_trade,
    ),
    Tool(
        name="team_cap_position",
        description=(
            "Where teams stand against the salary cap, tax level and both aprons this "
            "season, computed by the rules engine -- the same figures as the cap sheet. "
            "One call, every team unless you name some, sorted by room under the cap. "
            "Use it for any question about cap space, room, which teams are over or under "
            "a threshold, or how far a team is from one. Do not rebuild these totals from "
            "contract rows: they include cap holds and exclusions a sum of salaries misses."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "teams": {
                    "type": "array",
                    "items": {"type": "string", "description": "team key, e.g. DEN"},
                    "description": "Omit for all 30 teams.",
                }
            },
            "additionalProperties": False,
        },
        handler=_team_cap_position,
    ),
)

BY_NAME: dict[str, Tool] = {tool.name: tool for tool in TOOLS}


def specs() -> list[JsonDict]:
    """Every tool definition, for the model's tool list."""
    return [tool.spec() for tool in TOOLS]


def call(res: Resources, name: str, args: JsonDict) -> JsonDict:
    """
    Run a tool by name.

    An unknown tool name is an error returned to the model, not an exception:
    the loop should be able to correct itself within its retry budget rather
    than failing the user's question.
    """
    tool = BY_NAME.get(name)
    if tool is None:
        return {
            "ok": False,
            "error": f"no tool named {name!r}; available: {', '.join(sorted(BY_NAME))}",
        }
    try:
        return tool.handler(res, args)
    except (TypeError, AttributeError, KeyError, ValueError) as exc:
        # Arguments of the wrong shape -- a string where the schema wants an
        # object -- are the model's mistake to correct, the same as an unknown
        # tool name. Anthropic's models validate against the schema and never
        # did this; Nemotron Ultra (D23) sent `select` as a list of strings and
        # the TypeError failed the whole request. Narrow on purpose: anything
        # else is a defect here and should still surface as one.
        return {
            "ok": False,
            "error": (
                f"invalid arguments for {name}: {type(exc).__name__}: {exc}. "
                "Check them against the tool's input schema and call it again."
            ),
        }


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A record of one call, for the trace (task 6.10)."""

    name: str
    arguments: JsonDict
    result: JsonDict = field(default_factory=dict)
    error: str | None = None
