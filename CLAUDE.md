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
uv run mypy packages/engine/src packages/data/src packages/rag/src packages/agent/src
```

## Scrapers

`scraper/` holds six stdlib-only scrapers. They cache raw HTML, so re-runs cost
nothing. Read `scraper/README.md` before consuming any of their output — several
fields carry caveats that will produce wrong answers if ignored (Spotrac
snapshot dates span 13 months; `trade_exception.fromTeamId` is the counterparty,
not the holder).

## Planning docs

- [`docs/build-plan.md`](docs/build-plan.md) — phases and tasks
- [`docs/division-of-labor.md`](docs/division-of-labor.md) — who owns what, settled decisions D1–D12
