"""
The tools the model may call (task 6.2).

What these tests defend is the boundary, not the plumbing. A tool that accepts
a figure from the model, or answers a near miss as though it were a hit, breaks
ADR-001 while still looking like it works — so those are the properties
asserted here.
"""

from pathlib import Path

import pytest

from agent import tools
from agent.tools import Resources, call, specs
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

BASE_CAP = 136_021_000


@pytest.fixture(scope="module")
def res(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("agent")
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
        base_season_cap=BASE_CAP,
    )


# -- the boundary ---------------------------------------------------------


def test_no_tool_accepts_a_figure_from_the_model():
    """
    ADR-001's sharpest edge. A tool taking `outgoing_salary` would let the
    model pass a number it had invented, and the resulting answer would be
    wrong with nothing in the trace to show why. Tools take identifiers and
    look figures up.

    `limit` and the query DSL's own numeric arguments are not figures about the
    world -- they shape a result set, they do not assert anything.
    """
    allowed = {"limit", "value", "minimum", "maximum"}
    for tool in tools.TOOLS:
        properties = tool.input_schema.get("properties", {})
        for name, spec in properties.items():
            if name in allowed:
                continue
            assert spec.get("type") != "integer", (
                f"{tool.name}.{name} takes a number from the model"
            )


def test_every_tool_is_callable_and_declared_consistently():
    assert {t.name for t in tools.TOOLS} == set(tools.BY_NAME)
    assert {t.name for t in tools.TOOLS} == set(tools.HANDLERS)
    for spec in specs():
        assert spec["input_schema"]["type"] == "object"
        assert spec["description"].strip()


def test_an_unknown_tool_is_an_error_not_an_exception(res):
    """
    The loop should be able to correct itself inside its retry budget rather
    than failing the user's question.
    """
    result = call(res, "make_it_up", {})
    assert result["ok"] is False
    assert "no tool named" in result["error"]
    assert "resolve_provision" in result["error"]


def test_arguments_of_the_wrong_shape_are_an_error_not_an_exception(res):
    """
    The shape Nemotron Ultra sent (D23): `select` as bare strings, where the
    schema wants objects. It raised a TypeError and failed the whole request.
    """
    result = call(
        res,
        "query_league_data",
        {"entity": "contract_seasons", "select": ["salary"]},
    )
    assert result["ok"] is False
    assert "invalid arguments for query_league_data" in result["error"]


# -- resolution beats search (D14) ---------------------------------------


def test_a_named_rule_resolves_to_its_exact_citation(res):
    result = call(res, "resolve_provision", {"name": "Standard Traded Player Exception"})
    assert result == {
        "resolved": True,
        "citation": "Art. VII §6(j)(1)(i)",
        "named_as": "heading",
    }


def test_an_invented_name_is_refused_and_offers_real_ones(res):
    """
    The tool does not guess. A near miss answered as a hit would cite the wrong
    provision confidently, so candidates are offered for a retry instead.
    """
    result = call(res, "resolve_provision", {"name": "the trade exception thing"})
    assert result["resolved"] is False
    assert result["candidates"]
    assert all(isinstance(c, str) for c in result["candidates"])
    assert "citation" not in result


def test_resolution_is_case_insensitive_on_the_name(res):
    lower = call(res, "resolve_provision", {"name": "over 38 rule"})
    title = call(res, "resolve_provision", {"name": "Over 38 Rule"})
    assert lower == title
    assert lower["citation"] == "Art. VII §3(a)(2)"


# -- fetching text -------------------------------------------------------


def test_fetching_a_finer_citation_says_what_it_actually_returned(res):
    """
    The model must not claim to quote §2(e)(2)(i)(A) while holding §2(e)(2)(i).
    """
    result = call(res, "fetch_provision", {"citation": "Art. VII §2(e)(2)(i)(A)"})
    assert result["found"] is True
    assert result["substituted"] is True
    assert result["citation_returned"] == "Art. VII §2(e)(2)(i)"
    assert "may not engage in a transaction" in result["passages"][0]["text"]


def test_fetching_an_exact_citation_reports_no_substitution(res):
    result = call(res, "fetch_provision", {"citation": "Art. VII §6(j)(1)"})
    assert result["substituted"] is False
    assert result["citation_returned"] == "Art. VII §6(j)(1)"


def test_an_unknown_citation_is_refused_rather_than_approximated(res):
    result = call(res, "fetch_provision", {"citation": "Art. ZZ §99"})
    assert result["found"] is False
    assert "passages" not in result


def test_fetched_text_reports_the_figures_it_contains(res):
    """
    Task 5.9. The numbers are returned so they can be refused: almost every
    figure in this document belongs to a different exception, a worked example
    or a prior CBA than the one asked about.
    """
    result = call(res, "fetch_provision", {"citation": "Art. VII §6(j)(1)"})
    assert result["figures_present"]


# -- the structured query layer (ADR-002) --------------------------------


def test_a_query_returns_the_sql_that_produced_it(res):
    """A number whose derivation cannot be inspected is a number you cannot check."""
    result = call(
        res,
        "query_league_data",
        {
            "entity": "contract_seasons",
            "select": [{"field": "salary", "agg": "sum", "alias": "total"}],
            "filters": [
                {"field": "team", "op": "eq", "value": "DEN"},
                {"field": "season", "op": "eq", "value": "2026-2027"},
            ],
        },
    )
    assert result["ok"] is True
    assert result["rows"][0]["total"] > 100_000_000
    assert "SELECT" in result["sql"].upper()


def test_a_field_that_does_not_exist_is_refused_with_the_allowed_list(res):
    """
    Written for a model to act on. A bare "invalid query" burns a turn; naming
    what was allowed lets a bounded retry succeed.
    """
    result = call(
        res, "query_league_data", {"entity": "cap_holds", "select": [{"field": "salary"}]}
    )
    assert result["ok"] is False
    assert "unknown field" in result["error"]
    assert "Allowed:" in result["error"]


def test_the_entity_enum_is_generated_from_the_catalog():
    """
    So a renamed table cannot leave a stale schema the model still trusts.
    """
    from nbadata.query import ENTITIES

    schema = tools.BY_NAME["query_league_data"].input_schema
    assert schema["properties"]["entity"]["enum"] == sorted(ENTITIES)


def test_each_entitys_own_fields_are_described_to_the_model():
    """
    A flat "field: string" would let a query name cap_holds.salary, which does
    not exist, and the failure would look like an empty result.
    """
    description = tools.BY_NAME["query_league_data"].input_schema["properties"]["entity"][
        "description"
    ]
    assert "contract_seasons" in description
    assert "qualifying_offer" in description
    assert "bird_rights" in description


def test_malformed_query_arguments_do_not_raise(res):
    """The model will get this wrong; it must come back as a correctable error."""
    for args in ({}, {"entity": "contract_seasons"}, {"entity": "nope", "select": []}):
        result = call(res, "query_league_data", args)
        assert result["ok"] is False
        assert result["error"]


# -- entity resolution ---------------------------------------------------


def test_a_player_lookup_returns_candidates_not_a_guess(res):
    result = call(res, "lookup_player", {"name": "jokic"})
    assert result["candidates"]
    assert "unambiguous" in result


def test_an_ambiguous_player_is_flagged_rather_than_chosen(res):
    """
    6.3's rule: ambiguity triggers a clarification turn, never a guess.
    """
    result = call(res, "lookup_player", {"name": "williams"})
    if len(result["candidates"]) > 1:
        assert result["unambiguous"] is False


# -- definitions ---------------------------------------------------------


def test_a_defined_term_comes_back_with_its_citation(res):
    result = call(res, "define_term", {"term": "Apron Team Salary"})
    assert result["found"] is True
    assert result["citation"] == "Art. VII §2(e)(1)"


def test_a_term_the_agreement_does_not_define_is_refused(res):
    result = call(res, "define_term", {"term": "hard cap"})
    assert result["found"] is False
    assert "not a term this Agreement defines" in result["reason"]


# -- search is the fallback, and says so ---------------------------------


def test_search_marks_context_apart_from_what_matched(res):
    result = call(res, "search_cba", {"query": "traded player exception", "limit": 3})
    assert any(p["is_evidence"] for p in result["passages"])
    for passage in result["passages"]:
        assert passage["why"]


def test_the_search_tool_tells_the_model_to_prefer_resolution(res):
    """
    Measured in 5.8: resolution reaches the right provision every time,
    search 20% of the time on a paraphrase. The description has to say so or
    the model will reach for search first.
    """
    description = tools.BY_NAME["search_cba"].description
    assert "resolve_provision" in description
    assert "weaker" in description
