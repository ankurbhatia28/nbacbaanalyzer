# NBA CBA Analyzer

Ask a question about the NBA Collective Bargaining Agreement and get an answer a
rules engine can defend. **Live at https://nbacbaanalyzer.vercel.app** —
testers, start with [docs/testing.md](docs/testing.md).

```
"Can the Knicks trade Josh Hart to Phoenix for Devin Booker?"   → Not legal, and the exception it fails, quoted
"If I wanted to trade Embiid, what are the limitations the 76ers have?"
"Which team has the most cap space?"
"Should the Nuggets trade Jamal Murray?"                        → declined: allowed can be checked, wise cannot
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
| **Data** | "How much are the Nuggets committed for in 2026-27?" | Structured query DSL → SQL |
| **Validation** | "Is Jokić for Dončić legal?" | Rules engine → verdict + violations |
| **Constraints** | "What limits the 76ers in trading Embiid?" | Rules engine → applicable restrictions |

The model classifies and composes. Everything load-bearing is deterministic code
with tests.

Some questions are declined, with the reason: past seasons (only the current
snapshot is held, apart from the All-NBA, DPOY and MVP awards from 2020-21 that
decide max-salary eligibility), opinions about what a team *should* do, and
anything off topic. Contract details no source publishes — guarantees, trade
kickers, no-trade clauses — are **unknown, never zero**, and a verdict that
rests on one says so ([ADR-003](docs/adr/0003-unknown-is-not-zero.md)).

## Measured

Each number comes from a command in this repository, and the build plan
records how it was arrived at — including what was tried and made it worse.

| What | Result | How |
|---|---|---|
| Engine against real trades | **184 / 184** trades from four seasons with no failed check — 344 salary-matching checks pass; 75 need state the snapshot lacks and are skipped, not guessed | `python -m nbadata.evals`, blocking in CI (4.4) |
| Engine against illegal variants | **633 / 633** mutants caught, the reason right every time | the same run; boundary mutants sit $1 past the best lawful structure (4.6) |
| Question routing | **95–97%** exact-set on 60 questions; refusals 100% | `python -m agent.router_cli` (6.1) |
| Finding the right provision | **84%** of rules questions reach the text they are about | `python -m agent.intent_cli` (6.3) |
| Adversarial prompts | 30 attempts to make it compute, recall or skip a lookup: **0–4 misleading answers** across runs (2 on 2026-10-07), almost all a figure it worked out itself; never an uncited rule | `python -m agent.adversarial_cli` (6.11) |
| Plain retrieval, for contrast | recall@1 **34%**, recall@10 66% | `python -m rag.eval_cli` (5.8) — why the app names provisions rather than searching for them |
| Cost per question | rules ~$0.04, data ~$0.03–0.05, a trade ~$0.05–0.07 | measured live (8.0, 8.3); 97% of the answer step's input is served from cache (6.8) |

802 Python tests, including the CBA's own worked examples as golden tests and
property-based invariants over the engine. Five real traced sessions are in
[docs/traces/](docs/traces/).

## Layout

```
packages/engine    CBA rules. Pure functions, no LLM imports (CI-enforced).
packages/data      Scraper output → SQLite, plus the structured query DSL.
packages/rag       Structure-aware retrieval over the CBA text.
packages/agent     Routing, tools and the agent loop. The one package that calls a model.
apps/api           FastAPI over the agent, the cap sheet and the trade check.
apps/web           Next.js + TypeScript.
scraper/           Six data sources. See scraper/README.md.
docs/              Build plan, division of labor, ADRs.
```

## Design decisions

- [ADR-001 — The model does not compute, interpret, or recall](docs/adr/0001-the-model-does-not-decide.md)
- [ADR-002 — A structured query DSL, not text-to-SQL](docs/adr/0002-structured-query-not-text-to-sql.md)
- [ADR-003 — Unknown is not zero](docs/adr/0003-unknown-is-not-zero.md)
- [ADR-004 — Read-only at runtime](docs/adr/0004-read-only-at-runtime.md)

## Status

**Live at https://nbacbaanalyzer.vercel.app** (the API sleeps when idle and
takes about 30 seconds to wake). Rules engine, league database and query layer,
CBA retrieval, agent, API, and a web app with chat, a cap sheet per team and a
trade builder. What is left is in [docs/build-plan.md](docs/build-plan.md).

## Development

```bash
uv sync --all-packages --dev --extra langfuse     # the extra: traces reach Langfuse (8.5)
uv run pytest
uv run ruff check .

# Run it: build the two read-only artifacts, then the API, then the web app.
# The index needs the CBA PDF, which is not committed; rag.fetch downloads it.
uv run python -m rag.fetch                                # the CBA PDF, verified by hash (D20)
uv run python -m nbadata.ingest.load --out build/nbacba.db
uv run python -m rag --out build/cba-index.db
uv run --env-file .env uvicorn api.main:app --port 8000
cd apps/web && npm ci && npm run dev                      # http://localhost:3000

# The API as Render runs it (8.3): builds the artifacts inside the image
docker build -t nbacba-api . && docker run --rm -p 8000:8000 --env-file .env nbacba-api
```

Python 3.12+, Node 22. The API will not start without an Anthropic key in
`.env` (see `.env.example`), though only chat spends it: the cap sheet and
trade builder make no model call.

## The engine on its own

The rules engine is published separately as
[`nba-cba-engine`](packages/engine/README.md): no dependencies, no model, every
verdict cited.

```bash
pip install "nba-cba-engine @ git+https://github.com/ankurbhatia28/nbacbaanalyzer#subdirectory=packages/engine"
```

## License

[MIT](LICENSE) for the code. The Collective Bargaining Agreement is not
included, and the scraped data under `scraper/out/` comes from the sources
named in [`scraper/README.md`](scraper/README.md), under their own terms.
