# ADR-004: The application never writes to the league database

**Status:** Accepted · 2026-09-28

## Context

The app will be deployed publicly — Next.js on Vercel, FastAPI on Render.

Scraping, reconciliation and indexing are batch processes. Serving questions is
not. Conflating them would force a hosting posture the project does not
otherwise need: a managed database, a persistent disk, and migration machinery.

## Decision

The league database and the retrieval index are **build artifacts, not runtime
state**. The serving application opens them read-only and never writes.

- Ingest (Phase 2) runs in CI, producing `nbacba.db` and the retrieval index
  (the `artifacts` job, task 8.1).
- Deployment ships those artifacts alongside the code.
- Refreshing data is a rebuild and redeploy, not a migration.

Anything genuinely per-request — traces, rate-limit counters, cost accounting —
lives outside this database. Traces go to Langfuse (D16, which superseded
Raindrop under D4).

## Consequences

- Plain SQLite is sufficient in a serverless or container runtime; it is a file
  read. No Postgres, no connection pooling, no persistent disk.
- The league database is ~0.5 MB and the index ~4.5 MB (measured 2026-10-03;
  the first estimate here was ~2 MB and "a few MB"), so bundling is free
  relative to platform limits.
- Data currency is a deploy-time property, which makes the as-of provenance in
  the UI (task 7.6) mandatory rather than cosmetic.
- Reproducibility: the database is derivable from the scraper output in
  source control. **The index was not, until 8.1** — it is built from the CBA
  PDF, which is not committed. D20 closed that by pinning the PDF's sha256 and
  fetching it from an official copy (`python -m rag.fetch`), so both artifacts
  are now derivable from what the repository holds. The index build is
  byte-identical run to run.

## The failure this prevents

The tempting violation is small — "log each question to the database so we can
see what people ask." That single write turns a bundled file into shared mutable
state, and the app then needs a real database, a disk, and a migration story.
Per-request state goes elsewhere.
