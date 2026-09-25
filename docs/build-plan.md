# NBA Trade Engine — Build Plan

A CBA-grounded trade adjudicator, cap projector, and search engine. The architecture rests on one commitment: **a deterministic rules engine decides what is legal; the model only reads, parses, proposes, and explains.**

**Critical path: Phases 1 → 2 → 3**

### Sequencing note

Phases 1–3 are the project. A domain model, a rules engine, and an eval harness that scores the engine against every real trade since the 2023 CBA took effect — that alone is a stronger portfolio piece than any of the features that follow.

Phases 6–8 are the differentiators, but each is independently droppable. Build them in whichever order stays interesting; do not start any of them before Phase 3 reports a pass rate.

---

## 00 · Rails

*Boring setup that gets expensive to retrofit. One afternoon.*

- [ ] **0.1 — Scaffold the monorepo.** `packages/engine` (pure Python, zero LLM imports), `packages/rag`, `apps/api` (FastAPI), `apps/web` (Next.js). The engine must stay importable and testable with no network access.
- [ ] **0.2 — Toolchain:** `uv` for Python, `pnpm` for JS, pinned Python 3.12.
- [ ] **0.3 — Lint and type gates.** ruff + mypy in strict mode on `packages/engine` specifically. The engine is the part that must be provably correct; hold it to a higher bar than the app code.
- [ ] **0.4 — CI: lint, typecheck, unit tests.** Add the eval suite as a non-blocking job now, promote it to blocking once Phase 3 stabilizes.
- [ ] **0.5 — Single LLM client module with pinned model IDs in config.** Every model call routes through one wrapper. Makes swapping models, adding caching, and counting tokens a one-file change later.
- [ ] **0.6 — Structured logging plus request tracing from day one.** Retrofitting observability onto an agent loop is miserable. Trace tool calls, token counts, and latency per turn.
- [ ] **0.7 — Write ADR-001: "The model does not compute cap math."** A short architecture decision record. It is also the thesis of the README and the thing an interviewer will ask about.

---

## 01 · Domain model  `CRITICAL`

*Every later phase reads from these types. Modeling mistakes here surface as unfixable bugs in Phase 2.*

- [ ] **1.1 — `Season`: every league-wide dollar figure, per year.** Salary cap, tax line, first apron, second apron, the three MLE tiers, bi-annual exception, minimum salary scale by years of service, rookie scale by draft slot. All of it varies by season; none of it belongs hardcoded in logic.
- [ ] **1.2 — `Team` and `Player`.** Player needs years of service, draft year and slot, and birthdate — YOS drives minimum salaries and extension eligibility.
- [ ] **1.3 — `Contract` as a row per season, never a single salary field.** Each year carries: cap figure, guarantee status (full / partial / non-guaranteed with its date), option type (team, player, early termination), likely and unlikely incentives tracked separately, trade kicker percentage, no-trade clause.
- [ ] **1.4 — Contract type enum.** Rookie scale, veteran, max, minimum, two-way, Exhibit 10. Type changes which rules apply — minimum contracts have their own trade treatment.
- [ ] **1.5 — `CapHold`: free agent holds, roster charges, unsigned pick holds.** Holds are why cap salary and tax salary are different numbers. Getting this wrong makes every room-team calculation wrong.
- [ ] **1.6 — `BirdRights`: Full, Early, Non.** Derived from consecutive seasons without clearing waivers, and it transfers in a trade. Model the accrual, don't store a static label.
- [ ] **1.7 — `DraftPick` with protections as structured predicates.** `THORNY` Original team, current owner, year, round. Protection is a predicate over pick slot plus a conveyance rule (rolls to next year, converts to seconds, extinguishes). Swap rights are a separate entity, not a flag.
- [ ] **1.8 — `TradeException`: amount, creation date, expiry, eligibility.** Whether a TPE is usable depends on the team's current apron status and when it was created.
- [ ] **1.9 — `TradeRestriction` with reason and expiry date.** Recently signed, re-signed with a large raise, acquired via sign-and-trade, one-year Bird deal. Each has its own window; store the reason so the violation message can explain itself.
- [ ] **1.10 — Roster state:** 15 standard, 3 two-way, 14 minimum with grace period.
- [ ] **1.11 — Hand-build one complete team fixture before wiring real data.** A single team with every edge case represented — an option year, a non-guarantee, a trade kicker, a TPE, a protected pick. This fixture drives Phase 2 development and stays as a test asset.
- [ ] **1.12 — Emit JSON Schema for the whole model.** One contract shared by the engine, the API, the frontend, and the eval fixtures. Also becomes the basis for the agent's structured outputs in Phase 5.
- [ ] **1.13 — Attach `as_of` dates and a provenance field to all ingested data.** You will need this the moment someone asks why the app disagrees with Spotrac.

> **Done when** you can load a full 30-team league state from JSON, round-trip it through the schema, and query any team's roster and contract detail at an arbitrary date.

---

## 02 · Rules engine  `CRITICAL`

*Pure functions over Phase 1 types. No model calls anywhere in this package — enforce it with an import lint rule.*

- [ ] **2.1 — Read Articles I, VII, and X of the CBA end to end first.** Article I is definitions and it governs how every other article reads. Take notes with section references as you go — those notes become the citation constants in 2.17. Do not implement any rule below from memory, a blog post, or a summary article.
- [ ] **2.2 — Three salary totals: cap salary, tax salary, apron salary.** They are genuinely different numbers and diverge on holds, exceptions, and incentives. Most amateur cap tools conflate them.
- [ ] **2.3 — Apron classification.** Room team / over cap under tax / taxpayer / first apron / second apron. Everything downstream branches on this.
- [ ] **2.4 — Salary matching bands for over-cap teams.** `VERIFY FROM SOURCE` Transcribe the percentages and dollar offsets directly out of the CBA text. These changed with the 2023 agreement and most secondary sources online still describe the old tiers.
- [ ] **2.5 — Cap-space absorption path for room teams.** Room teams absorb into space first, then fall back to exception rules for any remainder. Different code path from 2.4, not a special case of it.
- [ ] **2.6 — First apron restrictions.** Cannot take back more salary than sent out, cannot acquire via sign-and-trade, no bi-annual exception, restrictions on signing bought-out players above a threshold.
- [ ] **2.7 — Second apron restrictions.** No aggregating salaries, no use of TPEs created in a prior season, no cash in trades, no taxpayer MLE, and the frozen/relocated future first-round pick consequence. This cluster is what makes modern trades hard and it is your app's whole reason to exist.
- [ ] **2.8 — Hard cap triggers.** Enumerate every action that sets a hard cap and at which apron it sets it. Then enforce the hard cap as a constraint for the rest of the league year.
- [ ] **2.9 — Stepien rule.** `THORNY` No leaving consecutive future first-rounders bare. Interacts nastily with swap rights and protections — a protected pick that may or may not convey makes "do you still own a first in year N" a non-trivial question.
- [ ] **2.10 — Base year compensation.**
- [ ] **2.11 — Poison pill provision.** Applies to players who signed a rookie-scale extension not yet in effect. Outgoing and incoming salary are valued differently for the two teams — a genuinely counterintuitive rule and a great demo case.
- [ ] **2.12 — Trade kickers.** Effect on both outgoing and incoming valuations, plus the reduction that applies when the receiving team lacks room to pay it.
- [ ] **2.13 — Trade date calendar.** December 15 and January 15 gates, the three-month / end-of-season rule for newly signed players, the two-month aggregation restriction on re-signed players with significant raises. All of it is date arithmetic against `as_of_date`.
- [ ] **2.14 — Simultaneous vs. non-simultaneous trades and TPE creation.** Includes the rule that a TPE cannot be combined with player salary in the same transaction.
- [ ] **2.15 — Multi-team trades.** Validate each team's outgoing and incoming independently rather than netting the whole deal. Support three- and four-team constructions; they are common and they are where naive trade machines break.
- [ ] **2.16 — Post-trade roster count and pick tradeability checks.** Roster minimums and maximums; the seven-years-out limit on trading future picks; already-traded and protection-conflicted picks.
- [ ] **2.17 — Violation code → CBA citation table.** `KEY JOIN` Every violation the engine can emit maps to a specific Article and Section. This single table is what connects the deterministic engine to the retrieval layer, and it is why your citations will be correct when a pure-RAG app's are not.
- [ ] **2.18 — Public API: `validate_trade(legs, as_of_date) -> TradeVerdict`.** Verdict carries `legal`, a list of violations each with code, citation, offending entity, and plain-English detail, plus derived effects (TPEs created, hard cap set, new apron status).
- [ ] **2.19 — Property-based tests on salary matching.** Hypothesis, generating random rosters and trades. Invariants like "a legal trade stays legal if you remove a pick" catch a surprising number of bugs.
- [ ] **2.20 — Hand-written golden tests from the CBA's own worked examples.** The document contains illustrative examples. They are free, authoritative test cases — use every one you find.

> **Done when** the engine validates your fixture team's trades correctly and every rule has a citation constant and at least one test.

---

## 03 · Ground-truth evals  `CRITICAL`

*Every completed trade was legal when it happened. That gives you hundreds of free, self-labeling test cases.*

- [ ] **3.1 — Scrape the transaction log.** Start with the 2023-24 season forward, so every case is governed by the current CBA. Extend backward later only if you also model the prior agreement.
- [ ] **3.2 — Normalize free-text transactions into structured trade legs.** Tedious and only partly automatable. Multi-team deals and cash considerations will need manual repair. Budget real time here.
- [ ] **3.3 — Reconstruct team state as of each trade date.** `SLEEPER HARD PROBLEM` You need rosters, contracts, exceptions, and apron status on the trade date, not today. This is the single most likely thing to stall the project. Mitigation: restrict v1 to deadline-day and offseason trades, where state is easier to pin down, and grow coverage from there.
- [ ] **3.4 — Assertion suite: every real trade returns legal.** Any failure is a bug in your engine, not in history. Pass rate over the corpus is the project's headline metric — put it in the README.
- [ ] **3.5 — Mutation generators for labeled negative cases.** Take a real legal trade and break it in one known way: inflate one side past the matching band, move a team over the second apron and make them aggregate, add a consecutive future first, shift the date into a restriction window. Each mutation carries its expected violation code.
- [ ] **3.6 — Score precision and recall on violation codes, not just the legal/illegal bit.** Rejecting a trade for the wrong reason is a failure. This metric is what makes the eval suite look serious.
- [ ] **3.7 — `make eval` emits a markdown report card; promote CI job to blocking.**

> **Done when** you can state a number like "passes 412/412 historical trades; 94% violation-code accuracy on 300 mutations" and defend how it was measured.

---

## 04 · CBA retrieval

*Retrieval over a hierarchical legal instrument, where the section number **is** the citation.*

- [ ] **4.1 — Acquire the current CBA PDF and record its version and date.**
- [ ] **4.2 — Structure-preserving parse: Article → Section → lettered and numbered subsections.** Naive PDF-to-text destroys the numbering, and the numbering is the whole value. Expect to write a custom parser against this document's specific layout.
- [ ] **4.3 — Chunk at subsection level with parent headings prepended.** Never split mid-subsection. A subsection read without its parent Section heading is frequently meaningless.
- [ ] **4.4 — Special handling for the Definitions article.** Index every defined term separately and attach relevant definitions to chunks that use them. "Salary" and "Team Salary" are terms of art and retrieval without them produces confidently wrong answers.
- [ ] **4.5 — Resolve cross-references into a graph.** Sections cite other sections constantly. Following one hop at retrieval time meaningfully improves answers.
- [ ] **4.6 — Hybrid retrieval: BM25 + embeddings, then rerank.** Legal text is dense with exact terms where lexical search beats semantic. Measure both arms separately so you can show the hybrid earned its complexity.
- [ ] **4.7 — Deterministic citation path from engine violations.** Violation code → canonical citation (from 2.17) → retrieve that exact section. The model quotes the provision; it never picks which provision applies. This is the architectural point of the whole project.
- [ ] **4.8 — Golden Q&A set of roughly 50 questions with expected citations.** Score recall@k and citation exact-match. Free-form retrieval is only for open questions like "what counts as a hardship exception" — never for numbers.
- [ ] **4.9 — Guardrail: numeric answers must originate from a tool result.**

---

## 05 · Agent layer

*Language in, structured calls out. The model's entire job is translation, proposal, and explanation.*

- [ ] **5.1 — Tool schemas.** `validate_trade`, `team_cap_sheet`, `player_lookup`, `find_salary_matches`, `search_cba`, `project_cap_sheet`, `simulate_pick`. Generate them from the Phase 1 JSON Schema rather than hand-writing them twice.
- [ ] **5.2 — Natural language → structured trade legs, with entity resolution.** `THORNY` "Ayton and a 2027 second for Grant" has to resolve to player IDs, teams, and pick objects. Fuzzy name matching, ambiguity handling, and an explicit clarification turn when a name is genuinely ambiguous.
- [ ] **5.3 — Structured outputs with schema validation and bounded retry.**
- [ ] **5.4 — Agent loop with a hard system-prompt rule against unaided arithmetic or rule claims.**
- [ ] **5.5 — Prompt caching on the stable prefix.** Tool definitions, the rules glossary, and league constants don't change between turns. Measure the cost delta and report it — cost engineering is a real skill signal.
- [ ] **5.6 — Streaming responses with tool-call progress surfaced in the UI.**
- [ ] **5.7 — Missing-data behavior.** When an option year or incentive is unknown, the answer says so and states the assumption it used. Never silently guess — the whole credibility of the app rests on this.
- [ ] **5.8 — Adversarial eval: ~30 prompts engineered to bait the model into doing cap math itself.** Assert it always calls the tool. This is a genuinely novel eval and worth writing about.

---

## 06 · Trade search

*Generate-and-verify: the model proposes shapes, the engine enumerates and filters, the model ranks what survives.*

- [ ] **6.1 — Team need vector: positional gaps, timeline, cap trajectory, roster construction.**
- [ ] **6.2 — Model proposes archetypes, never specific players.** "Expiring big in the $18–25M range" is a query the engine can execute. Asking the model to name players invites hallucinated salaries.
- [ ] **6.3 — Deterministic enumeration with staged pruning.** Salary band filter, then tradeability, then full legality check, then fit scoring. Order matters — the legality check is the expensive one, so it goes last among the hard filters.
- [ ] **6.4 — Complexity control.** Two-team search can be exhaustive. Three-team needs beam search seeded from two-team near-misses, where the salary gap is small enough that a third team could bridge it.
- [ ] **6.5 — Fit score — deliberately simple, and labeled as heuristic in the UI.** Resist the urge to build a player valuation model here. Anything you build will be contestable; being explicit that it's a heuristic is more credible than pretending otherwise.
- [ ] **6.6 — Mutual benefit constraint: both teams' objectives must improve or it isn't returned.**
- [ ] **6.7 — Model ranks and explains the surviving top N.**

---

## 07 · Cap sheet time machine

*Arguably more useful than trade analysis, and far fewer tools do it well.*

- [ ] **7.1 — Three-year projection with configurable cap growth.** Model the year-over-year cap increase cap as a constraint, and let the user vary the growth assumption.
- [ ] **7.2 — Cap hold generation and renouncement decision tree.**
- [ ] **7.3 — Options and guarantee dates as explicit branch points.**
- [ ] **7.4 — Extension eligibility windows.** Rookie-scale extensions, veteran extensions, and the designated veteran criteria with their timing rules. "When can we extend him and for how much" is a question fans ask constantly and no free tool answers well.
- [ ] **7.5 — Scenario tree UI: apply a hypothetical signing, see the downstream apron path.**
- [ ] **7.6 — Flag the season a team crosses each threshold and enumerate what it loses.**

---

## 08 · Protected pick simulation

*A top-4-protected 2027 first is not one asset — it's a distribution.*

- [ ] **8.1 — Team strength → win distribution.** Keep the prior simple. An over-engineered projection model here is scope creep dressed as rigor.
- [ ] **8.2 — Season simulation to lottery seeding, including tiebreakers.**
- [ ] **8.3 — Lottery draw simulation under current flattened odds.**
- [ ] **8.4 — Protection resolution and rollover across years.** A pick that doesn't convey rolls forward, sometimes with different protection, sometimes converting to seconds, sometimes extinguishing. This is where the Phase 1 predicate model earns its keep.
- [ ] **8.5 — Output a distribution over conveyance year and slot, never a point estimate.**
- [ ] **8.6 — Feed the expected value back into Stepien checking and trade search.**

---

## 09 · Interface

*The demo has to land in fifteen seconds for someone who has never heard of the second apron.*

- [ ] **9.1 — Trade builder: move players and picks between teams, live verdict as you go.**
- [ ] **9.2 — Violation panel: plain English, then the verbatim CBA quote, then the citation.** `THE DEMO` This is the screenshot that sells the project. Make it good.
- [ ] **9.3 — Cap sheet table with apron lines drawn as visible thresholds.** Tabular numerals, aligned columns. Money that doesn't line up reads as untrustworthy.
- [ ] **9.4 — Chat pane sharing state with the builder.** Ask a question about the trade currently on screen; edits from chat reflect in the builder.
- [ ] **9.5 — Rumor check: paste a proposal in plain text, get an adjudication.** The most shareable entry point in the whole app. A large share of proposals posted online are illegal, and nothing on the internet currently tells you why.
- [ ] **9.6 — Permalinks for a trade state.**
- [ ] **9.7 — Data provenance and as-of date visible on every cap figure.**
- [ ] **9.8 — Empty, loading, and error states; a usable read-only mobile view.**

---

## 10 · Ship

*The work only counts if someone can find it and understand it in two minutes.*

- [ ] **10.1 — Deploy API and web; publish the engine as a standalone installable package.** A pip-installable CBA rules engine with a test suite is a portfolio artifact in its own right, independent of the app.
- [ ] **10.2 — Rate limiting and a hard spend cap on the model key.**
- [ ] **10.3 — README leading with the architecture thesis and the eval numbers.** Not a feature list. Open with why the model doesn't do arithmetic, then the pass rate, then the diagram.
- [ ] **10.4 — Three-minute demo video: a real rumored trade getting rejected with a citation.**
- [ ] **10.5 — Write up the eval harness.** "I tested my rules engine against every NBA trade since 2023" is the post that gets shared. The harness is more interesting to engineers than the app is.

---

## Three ways this goes wrong

- **Historical state reconstruction (3.3) stalls the project.** It is the least glamorous task and the most likely to consume a month. Decide in advance what a reduced-scope version looks like — deadline-day trades only, one season only — and take it the moment you feel stuck.
- **Rules get implemented from secondary sources.** Blogs, forum posts, and older explainers describe the previous agreement. Anything numeric goes into the code with an Article and Section reference next to it, or it doesn't go in.
- **Feature sprawl before Phase 3 reports a number.** Trade search and Monte Carlo are more fun than salary-matching bands. Building them on an unvalidated engine produces a demo that is confidently wrong, which is worse than having fewer features.
