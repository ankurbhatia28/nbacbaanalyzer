# NBA CBA Analyzer — Build Plan

Ask a question about the NBA Collective Bargaining Agreement and get an answer a
rules engine can defend.

**The commitment:** the model parses, routes, and restates. It never computes,
never decides which rule applies, and never recalls a fact from memory.
See [ADR-001](adr/0001-the-model-does-not-decide.md).

## Four question kinds

Each routes to different machinery. The model classifies; everything
load-bearing is deterministic code with tests.

| Kind | Example | Handled by |
|---|---|---|
| **Rules** | "What counts as a hardship exception?" | Retrieval + citation (Phase 5) |
| **Data** | "How many players used Bird rights this season?" | Query DSL → SQL (Phase 2) |
| **Validation** | "Is Jokić for Dončić legal?" | Rules engine verdict (Phase 3) |
| **Constraints** | "What limits the 76ers in trading Embiid?" | Rules engine enumeration (Phase 3) |

## v1 scope

Current league state only. **No historical queries** — the data supports a
snapshot, not a timeline, and pretending otherwise produces confident wrong
answers. Questions needing history are refused with a reason.

**No hypotheticals.** "Is this trade legal" is checkable; "should they do it" is
opinion. The system answers the first and declines the second.

**Deployed, read-only.** The database and retrieval index are build artifacts the
app opens read-only — see [ADR-004](adr/0004-read-only-at-runtime.md). Data
currency is therefore a deploy-time property, which is why as-of provenance is a
required UI element rather than a nicety.

---

## Phase 0 — Rails ✅ Complete

- [x] **0.1** Monorepo: `packages/{engine,data,rag}`, `apps/{api,web}`
- [x] **0.2** uv workspace, Python 3.12+
- [x] **0.3** ruff + mypy (strict on engine), pytest
- [x] **0.4** GitHub Actions CI against `ankurbhatia28/nbacbaanalyzer`
- [x] **0.5** CI + unit test enforce that `packages/engine` imports no LLM client
- [x] **0.6** ADR-001 (model does not decide), ADR-002 (query DSL), ADR-003 (unknown is not zero)
- [x] **0.7** `.env.example`, `.gitignore`, rescoped README

---

## Phase 1 — Domain model

*Every later phase reads these types. Mistakes here surface as unfixable bugs in Phase 3.*

- [ ] **1.1** `Season` — cap, tax, both aprons, three MLE tiers, BAE, minimum scale by YOS, rookie scale by slot
- [ ] **1.2** `Team`, `Player` — including authoritative years of service from `roster_experience.csv`
- [ ] **1.3** `Contract` as a row per season — cap figure, guarantee status and date, option type, incentives, trade kicker, no-trade clause
- [ ] **1.4** Contract type enum — rookie scale, veteran, max, minimum, two-way, Exhibit 10
- [ ] **1.5** `CapHold` — free agent holds, roster charges, unsigned pick holds
- [ ] **1.6** `BirdRights` — Full / Early / Non, from `team_cap_hold.rightType`
- [ ] **1.7** `DraftPick` — protection as a structured predicate plus conveyance rule; swaps as their own entity
- [ ] **1.8** `TradeException` — amount, created, expiry, and apron-dependent usability
- [ ] **1.9** `TradeRestriction` — reason and expiry, so violations can explain themselves
- [ ] **1.10** Roster state — 15 standard, 3 two-way, 14 minimum with grace
- [ ] **1.11** **`Unknown` as a first-class type.** Tri-state present / absent / unknown for trade kickers, no-trade clauses, cash. Never coerced to zero — [ADR-003](adr/0003-unknown-is-not-zero.md)
- [ ] **1.12** Hand-built fixture team covering every edge case, before real data
- [ ] **1.13** JSON Schema for the whole model — one contract shared by engine, API, web, and evals
- [ ] **1.14** `as_of` and provenance on every ingested record

> **Done when** a full 30-team league state loads from the scraper CSVs, round-trips through the schema, and any team's roster and contract detail is queryable.

---

## Phase 2 — Data layer

*New in this scope. Data questions are a first-class surface, so the dataset needs to be queryable — safely.*

- [ ] **2.1** SQLite schema derived from the Phase 1 model
- [ ] **2.2** Ingest the six sources with explicit precedence rules per field
- [ ] **2.3** Cross-source reconciliation and a disagreement report
- [ ] **2.4** Entity resolution across sources — `bbref_id`, Fanspo `playerId`, Spotrac display names
- [ ] **2.5** Query DSL schema — entity, filters, grouping, aggregation ([ADR-002](adr/0002-structured-query-not-text-to-sql.md))
- [ ] **2.6** Deterministic DSL → SQL compiler
- [ ] **2.7** Validation with errors written for a model to act on, one bounded retry
- [ ] **2.8** Golden query tests — question → DSL → expected rows
- [ ] **2.9** `player_lookup` fuzzy search returning candidates, never a guess
- [ ] **2.10** Refuse what the DSL cannot express; log each refusal as a candidate extension

> **Done when** "how many players have Bird rights this season" returns a number, the DSL behind it is inspectable, and an unexpressible question is refused rather than approximated.

**Why not text-to-SQL:** a generated query that joins wrong produces a plausible number with no error anywhere — the same invisible failure as letting the model do arithmetic.

---

## Phase 3 — Rules engine

*Pure functions over Phase 1 types. No model calls — enforced by lint and CI.*

- [ ] **3.1** Read Articles I, VII, VIII and X from the PDF, taking section references as you go
- [ ] **3.2** Three salary totals — cap, tax, apron. They diverge on holds and exceptions.
- [ ] **3.3** Apron classification — room / over-cap / taxpayer / first apron / second apron
- [ ] **3.4** Salary matching bands — transcribed from the text, never from a summary
- [ ] **3.5** Cap-space absorption path for room teams
- [ ] **3.6** First apron restrictions
- [ ] **3.7** Second apron restrictions — aggregation, prior-year TPEs, cash, taxpayer MLE, frozen pick
- [ ] **3.8** Hard cap triggers, and enforcement for the rest of the league year
- [ ] **3.9** Stepien rule, accounting for swaps and protections
- [ ] **3.10** Base year compensation
- [ ] **3.11** Poison pill provision
- [ ] **3.12** Trade kickers — honouring `Unknown` rather than assuming zero
- [ ] **3.13** Trade date calendar — Dec 15, Jan 15, three-month and two-month restrictions
- [ ] **3.14** Simultaneous vs non-simultaneous trades and TPE creation
- [ ] **3.15** Multi-team trades — validate each team's send and receive independently
- [ ] **3.16** Roster counts and pick tradeability
- [ ] **3.17** **Violation code → CBA citation table.** The join between engine and retrieval; the reason citations are right
- [ ] **3.18** `validate_trade(legs, as_of) -> Verdict` with violations **and assumptions**
- [ ] **3.19** **`team_trade_constraints(team, player) -> Constraints`** — enumerate everything limiting a team, without a proposed deal. Answers the Embiid question.
- [ ] **3.20** Every verdict carries the assumptions it rests on (ADR-003)
- [ ] **3.21** Property-based tests on salary matching
- [ ] **3.22** Golden tests from the CBA's own worked examples

> **Done when** the fixture team validates correctly, every rule has a citation constant and a test, and `team_trade_constraints` explains a real team's situation in terms traceable to Articles.

---

## Phase 4 — Ground-truth evals

*Every completed trade was legal when it happened. Hundreds of free, self-labelling cases.*

- [ ] **4.1** Build the corpus from `player_transaction.csv` (814 records, 2025-10 → 2026-07)
- [ ] **4.2** Normalize free text into structured legs; ambiguous cases to `needs-review.jsonl`
- [ ] **4.3** Scope note: v1 validates against **current-state** reconstruction only. Trades needing state we lack are excluded and counted, not silently skipped.
- [ ] **4.4** Assertion: every real trade returns legal. Pass rate is the headline metric.
- [ ] **4.5** Mutation generators for labelled illegal cases, each with an expected violation code
- [ ] **4.6** Precision and recall on violation codes, not just the legal/illegal bit
- [ ] **4.7** Query DSL eval set — golden questions with expected results
- [ ] **4.8** `make eval` → markdown report card; promote the CI job to blocking

> **Done when** you can state "passes N/N reconstructible trades, M% violation-code accuracy" and defend how it was measured.

---

## Phase 5 — CBA retrieval

- [ ] **5.1** Extract with **PyMuPDF**, not pypdf — zero word-boundary defects, ~5× faster
- [ ] **5.2** Build the unit tree from the PDF's own **2,412-entry bookmark outline** (42 Articles, 288 Sections, 938 subsections, pp. 1–671). Traversal, not heuristic parsing.
- [ ] **5.3** Sub-split the 39 oversized Section units at outline level 3–4
- [ ] **5.4** **Definitions index.** Article I terms of art govern every other Article; attach relevant definitions to chunks that use them
- [ ] **5.5** Cross-reference graph with one-hop expansion at retrieval time
- [ ] **5.6** **BM25 first** (SQLite FTS5, no model at inference). Legal text is dense with exact terms of art where lexical search wins. Add embeddings only if measured retrieval gains justify the cold-start and bundle cost — measure both arms separately and report the delta.
- [ ] **5.7** **Deterministic citation path:** violation code → canonical citation → fetch that unit verbatim. The model quotes; it never chooses.
- [ ] **5.8** Golden Q&A set (~50) with expected citations; score recall@k and citation exact-match
- [ ] **5.9** Guardrail: numeric answers must originate from a tool result, never from retrieved prose

---

## Phase 6 — Agent layer

- [ ] **6.1** **Question router** — classify into rules / data / validation / constraints, allowing combinations
- [ ] **6.2** Tool schemas generated from the Phase 1 JSON Schema
- [ ] **6.3** NL → structured intent with entity resolution; ambiguity triggers a clarification turn, not a guess
- [ ] **6.4** Structured outputs, schema validation, bounded retry
- [ ] **6.5** Agent loop with a hard prohibition on unaided arithmetic or rule assertions
- [ ] **6.6** **Refusal policy** — hypotheticals ("should they?"), historical questions (out of v1 scope), and anything the tools cannot answer. Each refusal states why.
- [ ] **6.7** Assumptions surfaced in the answer, not buried
- [ ] **6.8** Prompt caching on the stable prefix; measure the cost delta
- [ ] **6.9** Streaming, with tool-call progress visible
- [ ] **6.10** **Tracing via Raindrop — one trace per user session.** Each trace carries the user input, system prompt, every tool call and result, retrieved context, every intermediate model call, and the final user-facing output.
- [ ] **6.11** Adversarial eval — ~30 prompts engineered to bait the model into doing cap math or asserting a rule unaided. Assert it always calls the tool.
- [ ] **6.12** Cost and latency tracking per request
- [ ] **6.13** **Rate limiting and a hard spend cap**, built with the agent loop rather than bolted on at deploy. A public URL in front of a model key is not deployable without them.

---

## Phase 7 — Interface

- [ ] **7.1** Chat as the primary surface — questions, not forms
- [ ] **7.2** **Answer card**: verdict, plain English, verbatim CBA quote, citation, assumptions
- [ ] **7.3** Show the structured query behind any number, inspectable on demand
- [ ] **7.4** Trade builder with live verdict, reachable from a chat answer
- [ ] **7.5** Cap sheet view with apron lines as visible thresholds, tabular numerals
- [ ] **7.6** **Provenance and as-of date on every figure — mandatory.** The dataset is a snapshot, and the Spotrac rows alone span 13 months of differing snapshot dates. A public app implies currency; without prominent as-of labelling it is quietly misleading.
- [ ] **7.7** Permalinks for a question and its answer
- [ ] **7.8** Empty, loading, error and refusal states; usable read-only mobile view

---

## Phase 8 — Ship

**Next.js → Vercel. FastAPI → Render.** The engine, data and rag packages stay
platform-agnostic; only `apps/` knows where it runs.

- [ ] **8.1** **Build pipeline in CI** — run ingest and indexing, emit `nbacba.db` and the retrieval index as deployment artifacts ([ADR-004](adr/0004-read-only-at-runtime.md)). Keeps them out of git and makes the whole dataset reproducible from source.
- [ ] **8.2** Deploy `apps/web` to Vercel
- [ ] **8.3** Deploy `apps/api` to Render, with the artifacts from 8.1 bundled
- [ ] **8.4** Publish `packages/engine` as a standalone installable package — a tested CBA rules engine is a portfolio artifact independent of the app
- [ ] **8.5** Environment and secrets per platform; confirm the spend cap from 6.13 is live
- [ ] **8.6** Cold-start note: Render's free tier spins down after inactivity. Either pay for always-on or accept a slow first load on a résumé link.
- [ ] **8.7** README leading with the architecture thesis and the eval numbers
- [ ] **8.8** Three-minute demo: a rumoured trade adjudicated with a citation, and a question refused with a reason
- [ ] **8.9** Write-up on the eval harness and the deterministic citation path

## v2 — deferred

Not in v1. Listed so they stay out of scope rather than drifting in.

- **9. Cap sheet projection** — multi-year, options as branch points, extension eligibility windows
- **10. Trade search** — archetype proposal, deterministic enumeration, mutual-benefit constraint
- **11. Historical data** — Spotrac archive passes for prior seasons; unlocks "past two seasons" questions
- **12. Protected pick simulation** — lottery Monte Carlo over protection predicates
- **13. Live statistics** — show on-court comparison alongside a trade. **Presents, never concludes.** No "who wins this trade."

---

## Three ways this goes wrong

- **The model starts deciding.** Every rule assertion or number that does not trace to a tool result is a defect, however plausible it reads. The adversarial eval (6.11) exists for this.
- **Unknowns get defaulted.** A trade kicker silently treated as zero produces a clean verdict on an illegal trade, with nothing indicating a guess. ADR-003 is load-bearing, not a footnote.
- **Scope drifts back toward analysis.** "Who won this trade" and "should they do it" are the most tempting features and the least defensible. They are v2 at the earliest, and presentational even then.
