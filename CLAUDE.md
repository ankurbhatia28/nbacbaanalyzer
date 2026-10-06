# Working conventions

## Git

**Never commit or push directly to `main`.** Branch, push the branch, open a PR,
let the repo owner merge.

```bash
git checkout -b phase-1-domain-model
# ... work ...
git push -u origin phase-1-domain-model
gh pr create --fill
```

Branch names: `phase-N-<slug>` for plan work, `fix/<slug>` and `chore/<slug>`
otherwise. CI runs on pull requests, so the green check is visible before merge.

**Check `gh pr list` before branching off `main`.** A green PR is not a merged
one, and merge state lives on GitHub rather than in the conversation or in any
file here. Branching off `main` while an approved PR is still open produces
edits against a stale file, which fail in confusing ways — this happened twice.
If an open PR contains work the next change depends on, say so and stop rather
than stacking: a stack whose base merges first strands everything above it.

**Stash before you reset.** `git reset --hard` with uncommitted work destroys
it, and `git stash push -u` first costs nothing.

## Architectural constraints

These are enforced, not aspirational. Breaking them fails CI.

- **`packages/engine`, `packages/data` and `packages/rag` import no LLM
  client.** `packages/agent` is the one package that may. Checked by CI and by
  `tests/test_architecture.py`, which parses imports rather than matching text.
  See [ADR-001](docs/adr/0001-the-model-does-not-decide.md).
- **No `.env` file is ever tracked** except `.env.example`. Checked by CI.
- **Unknown is never zero.** Trade kickers, no-trade clauses and cash
  considerations are tri-state. A verdict resting on an unknown must say so.
  See [ADR-003](docs/adr/0003-unknown-is-not-zero.md).
- **The app never writes to the league database.** It and the retrieval index
  are read-only build artifacts. See [ADR-004](docs/adr/0004-read-only-at-runtime.md).

## Commands

```bash
uv sync --all-packages --dev
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy packages/engine/src packages/data/src packages/rag/src packages/agent/src apps/api/src

# Run it locally: build the two artifacts, then the API, then the web app
uv run python -m rag.fetch                                # the CBA PDF, verified by hash (D20)
uv run python -m nbadata.ingest.load --out build/nbacba.db
uv run python -m rag --out build/cba-index.db
uv run --env-file .env uvicorn api.main:app --port 8000
cd apps/web && npm ci && npm run dev                      # http://localhost:3000

# The API as Render runs it (8.3): builds the artifacts inside the image
docker build -t nbacba-api . && docker run --rm -p 8000:8000 --env-file .env nbacba-api

# Web app checks (apps/web)
npm run typecheck && npm test && npm run build
```

`apps/web` is not a uv workspace member: the workspace lists `apps/api`
explicitly, because a glob over `apps/*` matches the Node app and breaks every
`uv` command.

## Scrapers

`scraper/` holds six stdlib-only scrapers. They cache raw HTML, so re-runs cost
nothing. Read `scraper/README.md` before consuming any of their output — several
fields carry caveats that will produce wrong answers if ignored (Spotrac
snapshot dates span 13 months; `trade_exception.fromTeamId` is the counterparty,
not the holder).

## Planning docs

- [`docs/build-plan.md`](docs/build-plan.md) — phases and tasks. **Opens with a
  "where this stands" header**; read it before planning anything.
- [`docs/division-of-labor.md`](docs/division-of-labor.md) — who owns what, and
  settled decisions **D1–D24**
- [`docs/traces/`](docs/traces/) — five real sessions, committed because hosted
  retention is 30 days

These are the project's memory. A session that reads them is nearly as
well-oriented as one that was here for the whole build, which is what makes it
cheap to start a fresh session at a phase boundary. **Keep them current**: a
stale checkbox is worse than no checkbox, because the next session believes it.

Record what was *tried and rejected*, with the number that killed it, not just
what shipped. Several decisions here rest on measurements that came out the
wrong way — a document-frequency stop list that made recall worse, indexing
definition text that halved it, a guarantee derivation that validated at 2 of 30.
