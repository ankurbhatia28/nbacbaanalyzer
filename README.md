# NBA CBA Analyzer

Ask a question about the NBA Collective Bargaining Agreement and get an answer a
rules engine can defend.

```
"If I wanted to trade Embiid, what are the limitations the 76ers have?"
"Is trading Jokić for Dončić straight up a valid trade?"
"How many players re-signed using Bird rights in the past two seasons?"
"Why can't the Suns aggregate salaries in a trade?"
```

## The thesis

The CBA is a ~676-page legal instrument governing a deterministic arithmetic
system. Questions about it have right answers that can be checked — which makes
it one of the few domains where an LLM application can be held to a real
standard instead of a plausible-sounding one.

So the model never decides anything:

| | |
|---|---|
| **Computation** | A deterministic rules engine. No model arithmetic, ever. |
| **Rule selection** | The engine emits a violation code; a static table maps it to an Article and Section. The model never picks which provision applies. |
| **Facts** | Every number enters through a tool result. Nothing from model memory. |
| **The model's job** | Parse the question into structured intent, route it, and restate what the tools returned. |

A language model asked "is this trade legal?" is right most of the time. Most of
the time is the worst possible accuracy — the wrong answers look exactly like
the right ones. See [ADR-001](docs/adr/0001-the-model-does-not-decide.md).

## How a question gets answered

Questions fall into four kinds, and each routes to different machinery:

| Kind | Example | Handled by |
|---|---|---|
| **Rules** | "What counts as a hardship exception?" | Retrieval over the CBA, with citations |
| **Data** | "How many players used Bird rights last season?" | Structured query DSL → SQL |
| **Validation** | "Is Jokić for Dončić legal?" | Rules engine → verdict + violations |
| **Constraints** | "What limits the 76ers in trading Embiid?" | Rules engine → applicable restrictions |

The model classifies and composes. Everything load-bearing is deterministic code
with tests.

## Layout

```
packages/engine    CBA rules. Pure functions, no LLM imports (CI-enforced).
packages/data      Scraper output → SQLite, plus the structured query DSL.
packages/rag       Structure-aware retrieval over the CBA text.
apps/api           FastAPI. Tool definitions and the agent loop.
apps/web           Next.js + TypeScript.
scraper/           Six data sources. See scraper/README.md.
docs/              Build plan, division of labor, ADRs.
```

## Design decisions

- [ADR-001 — The model does not compute, interpret, or recall](docs/adr/0001-the-model-does-not-decide.md)
- [ADR-002 — A structured query DSL, not text-to-SQL](docs/adr/0002-structured-query-not-text-to-sql.md)
- [ADR-003 — Unknown is not zero](docs/adr/0003-unknown-is-not-zero.md)

## Status

Data collection complete across six sources. Engine, query layer, retrieval and
agent are in progress. See [docs/build-plan.md](docs/build-plan.md).

## Development

```bash
uv sync --all-packages --dev
uv run pytest
uv run ruff check .
```

Python 3.12+. Everything runs locally; no hosted services are required.
