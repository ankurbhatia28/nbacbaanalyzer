"""
The HTTP routes, driven through FastAPI's test client with a scripted caller.

No key and no network. What is pinned: the JSON and streaming routes return
the same card for the same run, the stream shows progress before the card, a
cap refusal arrives as a card that says why, and a bad request is refused
before anything is spent.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.budget import Budget
from agent.llm import Reply, ToolRequest, Usage
from agent.models import Role
from agent.tools import Resources
from agent.trace import FileExporter
from api.app import MAX_QUESTION_CHARS, Service, create_app
from nbadata.db import build, open_readonly
from rag.outline import DEFAULT_PDF

CSV_DIR = Path(__file__).resolve().parents[3] / "scraper" / "out"
needs_data = pytest.mark.skipif(
    not DEFAULT_PDF.exists() or not (CSV_DIR / "contracts.csv").exists(),
    reason="CBA PDF or scraper output not present",
)


class Script:
    """Answers each role from a script, the way test_stream's fake does."""

    def __init__(self, *, intents, basis=None, answers=()):
        self.routing = json.dumps({"intents": intents, "reason": "r", "refusal_basis": basis})
        self.answers = list(answers)

    def __call__(self, *, role, system, messages, max_tokens=1024, tools=None) -> Reply:
        if role is Role.ROUTER:
            return Reply(self.routing, Usage(10, 5), "stub")
        if role is Role.INTENT:
            plan = {"provisions": [], "players": [], "teams": [], "reason": "r"}
            return Reply(json.dumps(plan), Usage(10, 5), "stub")
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


@pytest.fixture
def empty(tmp_path):
    """Schema only. Enough for any run that refuses before reading data."""
    build(tmp_path / "league.db").close()
    return Resources(
        league=open_readonly(tmp_path / "league.db"),
        cba=sqlite3.connect(":memory:", check_same_thread=False),
        base_season_cap=136_021_000,
    )


def client(res, caller, **kw) -> TestClient:
    return TestClient(create_app(Service(res=res, caller=caller, **kw)))


def events(response) -> list[tuple[str, dict]]:
    out = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def test_the_bare_url_leads_somewhere_useful_rather_than_a_404(empty):
    response = client(empty, Script(intents=["rules"])).get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/docs"


def test_health_reports_the_dataset_and_the_card_schema(empty):
    body = client(empty, Script(intents=["rules"])).get("/health").json()
    assert body["ok"] is True
    assert body["schema"] == 1
    assert body["dataset"] == {"built_at": None, "season": None, "source_dates": {}}


def test_a_refusal_is_a_card_with_the_decision_behind_it(empty):
    response = client(empty, Script(intents=["refused"], basis="historical")).post(
        "/ask", json={"question": "Who led the league in cap space in 2019?"}
    )
    assert response.status_code == 200
    card = response.json()
    assert card["status"] == "refused"
    assert "D6" in card["refusal_basis"]


def test_a_cap_refusal_is_a_card_not_an_empty_429(empty):
    """The reason belongs in front of the user."""
    api = client(empty, Script(intents=["refused"], basis="opinion"), budget=Budget(max_requests=1))
    api.post("/ask", json={"question": "first"})
    card = api.post("/ask", json={"question": "second"}).json()
    assert card["status"] == "unavailable"
    assert "rate limit" in card["text"]


@pytest.mark.parametrize("question", ["", "x" * (MAX_QUESTION_CHARS + 1)])
def test_a_bad_question_is_rejected_before_any_model_call(empty, question):
    calls = []

    def caller(**kw):
        calls.append(kw)
        raise AssertionError("must not be called")

    response = client(empty, caller).post("/ask", json={"question": question})
    assert response.status_code == 422
    assert calls == []


def test_the_stream_ends_in_the_card_the_json_route_returns(empty):
    script = lambda: Script(intents=["refused"], basis="opinion")  # noqa: E731
    body = {"question": "Should the Bucks trade Giannis?"}
    plain = client(empty, script()).post("/ask", json=body).json()
    streamed = events(client(empty, script()).post("/ask/stream", json=body))

    assert streamed[0][0] == "started"
    name, card = streamed[-1]
    assert name == "card"
    assert card == plain


def test_every_run_exports_its_trace(empty, tmp_path):
    exporter = FileExporter(tmp_path / "traces.jsonl")
    client(empty, Script(intents=["refused"], basis="opinion"), exporter=exporter).post(
        "/ask", json={"question": "Should they?"}
    )
    assert exporter.written == 1


def test_cors_is_off_unless_origins_are_given(empty):
    app = create_app(Service(res=empty, caller=Script(intents=["rules"])))
    response = TestClient(app).options(
        "/ask", headers={"origin": "https://x.example", "access-control-request-method": "POST"}
    )
    assert "access-control-allow-origin" not in response.headers


# -- a full run, on the real artifacts ---------------------------------


@pytest.fixture(scope="module")
def real(tmp_path_factory):
    from nbadata.ingest.load import load as load_csvs
    from rag import index as ix
    from rag.chunks import build as build_chunks
    from rag.crossrefs import build as build_graph
    from rag.definitions import build as build_definitions
    from rag.outline import load

    tmp = tmp_path_factory.mktemp("api")
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


@needs_data
def test_a_streamed_data_answer_shows_progress_then_a_card_with_provenance(real):
    query = {
        "entity": "contract_seasons",
        "select": [{"field": "salary", "agg": "sum"}],
        "filters": [
            {"field": "team", "op": "eq", "value": "DEN"},
            {"field": "season", "op": "eq", "value": "2026-2027"},
        ],
    }
    fetch = {"citation": "Art. VII §6(j)(1)"}
    script = Script(
        intents=["data"],
        answers=[
            [("query_league_data", query), ("fetch_provision", fetch)],
            "Denver is committed for $208,710,566 in 2026-27 (Art. VII §6(j)(1)).",
        ],
    )
    streamed = events(client(real, script).post("/ask/stream", json={"question": "Nuggets?"}))
    names = [name for name, _ in streamed]

    assert names.index("tool") < names.index("card")
    card = streamed[-1][1]
    assert card["status"] == "answered"
    assert card["verified"] is True
    (figure,) = card["figures"]
    assert figure["in_answer"] == ["$208,710,566"]
    assert figure["provenance"][0]["basis"] == "scraped"
    assert card["quotes"][0]["cited_in_answer"] is True
    assert card["dataset"]["source_dates"]["bbref_contracts"]


def test_development_defaults_cors_to_the_local_web_app_and_nowhere_else(monkeypatch):
    from api.origins import allowed_origins

    monkeypatch.delenv("NBACBA_ALLOWED_ORIGINS", raising=False)
    assert allowed_origins("development") == ["http://localhost:3000"]
    assert allowed_origins("production") == []
    monkeypatch.setenv("NBACBA_ALLOWED_ORIGINS", "https://a.example, https://b.example")
    assert allowed_origins("production") == ["https://a.example", "https://b.example"]
    monkeypatch.setenv("NBACBA_ALLOWED_ORIGINS", "")
    assert allowed_origins("development") == []


def test_too_many_quote_labels_are_refused(empty):
    response = client(empty, Script(intents=["rules"])).post("/quotes", json={"labels": ["x"] * 65})
    assert response.status_code == 422


@needs_data
def test_quotes_come_back_verbatim_by_label_and_never_as_a_near_miss(real):
    """
    The permalink contract (7.7): a passage label resolves to exactly the text a
    tool returned for it, a repeated citation's "(passage N)" label to its own
    chunk, and a label no longer in the index to nothing.
    """
    from agent.tools import call

    fetched = call(real, "fetch_provision", {"citation": "Art. VII §6(j)(1)"})
    labels = [p["citation"] for p in fetched["passages"]]
    repeated = real.cba.execute("SELECT citation FROM chunks WHERE ordinal = 2 LIMIT 1").fetchone()[
        0
    ]
    labels += [f"{repeated} (passage 2)", "Art. XCIX §1"]

    texts = (
        client(real, Script(intents=["rules"]))
        .post("/quotes", json={"labels": labels})
        .json()["texts"]
    )
    for passage in fetched["passages"]:
        assert texts[passage["citation"]] == passage["text"]
    second = real.cba.execute(
        "SELECT body FROM chunks WHERE citation = ? AND ordinal = 2", (repeated,)
    ).fetchone()[0]
    assert texts[f"{repeated} (passage 2)"] == second
    assert texts["Art. XCIX §1"] is None
