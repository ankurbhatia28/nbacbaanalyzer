# Division of Labor

Companion to [`build-plan.md`](./build-plan.md). Task numbering matches that file exactly.

> **Status (2026-10-05): Phases 0–7 complete; Phase 8 (Ship) under way — 8.0 done.** Where things stand, and what Phase 8 needs decided first, is in the header of [`build-plan.md`](./build-plan.md). This file's §1 inventory, §2 ownership table and §6 decisions (D1–D23) are current; §4.3, §5 and §7 are kept as the record of how the work was planned in Phase 0 and are not a to-do list. Scrapers and caveats: [`scraper/README.md`](../scraper/README.md).

**Legend**

| Marker | Meaning |
|---|---|
| `CLAUDE` | I can do this end to end. You review the output. |
| `YOU` | Requires an account, a credential, a judgment call, or physical access to something I can't reach. |
| `BOTH` | I produce a draft; you verify or decide. Named explicitly because a silent handoff here is how errors ship. |

---

## 1. Input status

| # | Input | Status |
|---|---|---|
| B1 | CBA PDF | **Done** — 676 pages |
| B2 | Season constants | **Done** — `salary_cap_figure.csv`, 2011-12 → 2034-35 |
| B3 | Contract data | **Done** — see the inventory below; only no-trade clauses remain |
| B4 | Draft picks + protections | **Done** — 616 rows with full protection prose, plus Spotrac as a second source |
| B5 | Anthropic API key | **Done** — in `.env` (untracked); used since Phase 6 |
| B6 | Player birthdates | **Done** — 461 rows |
| B7 | Award history | **Done** — 102 rows, **2020-21 → 2025-26** |

B7 was extended back to 2020-21 after the fact: Higher Max Criteria looks at "the immediately preceding Season or two of the preceding three," so adjudicating a 2023-24 trade needs 2020-21 awards. The original 2023-24-forward pull would have silently failed that lookback.

### Data inventory

| Source | Files | Carries |
|---|---|---|
| **Fanspo** | `draft_pick`, `team_cap_hold`, `trade_exception`, `player_info`, `player_transaction`, `team_payroll_player`, `team_profile`, `player_lebron`, `salary_cap_figure` | Draft picks + protection prose, cap holds with Bird rights, birthdates, 814 transactions, season constants back to 2011-12, team strength inputs |
| **B-R contracts** | `contracts`, `contract_totals`, `contract_notes` | 1,124 player-seasons, 365 option-years, 349 signing dates, guaranteed remaining |
| **B-R awards** | `awards` | All-NBA / DPOY / MVP, 2020-21 → 2025-26 |
| **B-R rosters** | `roster_experience` | Authoritative years of service (661 players), birth dates |
| **SalarySwish** | `salaryswish_hard_caps`, `salaryswish_trade_legs` | Hard-cap ceilings with their triggering transaction, mapped to Transaction Restrictions Table rows; trades with **cash amounts and direction** |
| **Spotrac (archive)** | `spotrac_decisions`, `spotrac_roster`, `spotrac_cap_holds`, `spotrac_trade_exceptions` | 30/30 teams. Guarantee **dates**, extension-eligibility dates, qualifying offers, TPE original-vs-available. **Not** trade kickers (column empty league-wide) and effectively not incentives. Snapshot dates span 13 months — see `scraper/README.md`. |

Three sources independently cover draft picks, cap holds, trade exceptions and contract type. That redundancy is worth keeping — cross-source disagreement is a cheap correctness signal, and it already caught two real bugs (§1 caveats, and the option-signal gap in `scraper/README.md`).

## 2. Phase-by-phase ownership

Phases renumbered for the rescope — see [`build-plan.md`](./build-plan.md). Phase 0 is complete.

### Phase 1 — Domain model

| Task | Owner | Notes |
|---|---|---|
| 1.1–1.10 core types | `CLAUDE` | All source data in hand |
| 1.11 `Unknown` tri-state | `CLAUDE` | ADR-003. The type that keeps the engine honest. |
| 1.12 Fixture team | `CLAUDE` | **Worth your review** — an edge case missing here is never tested in Phase 3 |
| 1.13 JSON Schema | `CLAUDE` | — |
| 1.14 Provenance | `CLAUDE` | — |

### Phase 2 — Data layer

| Task | Owner | Notes |
|---|---|---|
| 2.1–2.4 schema, ingest, reconciliation, entity resolution | `CLAUDE` | **Source precedence is a judgment call** — I'll propose a per-field ranking for you to confirm |
| 2.5–2.7 DSL, compiler, validation | `CLAUDE` | ADR-002 |
| 2.8 Golden query tests | `BOTH` | I write them; **you sanity-check the expected answers** — a wrong gold label makes a broken query layer look correct |
| 2.9–2.10 lookup, refusals | `CLAUDE` | — |

### Phase 3 — Rules engine

| Task | Owner | Notes |
|---|---|---|
| 3.1 Read the CBA | `BOTH` | See §3. Extraction is solved; the ~15-constant verification pass is still yours. |
| 3.4 Salary matching bands | `BOTH` | **You spot-check.** Most load-bearing constant in the codebase. |
| 3.7 Second apron restrictions | `BOTH` | **You spot-check.** Second on that list. |
| 3.8 Hard cap triggers | `BOTH` | I enumerate; you confirm the list is complete |
| 3.17 Violation → citation table | `BOTH` | **You audit.** A wrong citation misinforms confidently and no test catches it. |
| 3.19 `team_trade_constraints` | `BOTH` | New tool. **You define what a useful answer looks like** for "what limits the 76ers" — I can build it, but you know what a fan actually wants to see. |
| All other 3.x | `CLAUDE` | Written from the PDF with citations |

### Phase 4 — Ground-truth evals

| Task | Owner | Notes |
|---|---|---|
| 4.1–4.2 corpus, normalization | `BOTH` | Ambiguous legs land in `needs-review.jsonl` for you — expect 20–40 |
| 4.3 Scope note | `CLAUDE` | Excluded trades are counted, never silently dropped |
| 4.4–4.8 assertions, mutations, scoring, CI | `CLAUDE` | — |

### Phase 5 — CBA retrieval

| Task | Owner | Notes |
|---|---|---|
| 5.1–5.3 extraction, outline traversal | `CLAUDE` | Solved — PyMuPDF plus the PDF's own outline |
| 5.4–5.7 definitions, cross-refs, hybrid retrieval, citation path | `CLAUDE` | — |
| 5.8 Golden Q&A | `BOTH` | I draft ~50; **you review the expected citations** |
| 5.9 Numeric guardrail | `CLAUDE` | — |

### Phase 6 — Agent layer

| Task | Owner | Notes |
|---|---|---|
| 6.1–6.5 routing, tools, intent, loop | `CLAUDE` | Needs **B5 (API key)** |
| 6.6 Refusal policy | `BOTH` | I implement; **you own the wording** — a refusal is a product surface, not an error |
| 6.7–6.9 assumptions, caching, streaming | `CLAUDE` | — |
| 6.10 Tracing | `BOTH` | Done, on **Langfuse Cloud Hobby (D16)**, which superseded Raindrop (D13). Keys in `.env` (untracked); without them traces are written locally. |
| 6.11 Adversarial eval | `BOTH` | I write ~30 bait prompts; **add any phrasings a real fan would use** |
| 6.12 Cost tracking | `CLAUDE` | — |

### Phase 7 — Interface

| Task | Owner | Notes |
|---|---|---|
| 7.0 API + answer-card contract | `CLAUDE` | Done. The card's fields are the contract the web app renders; **worth your review before the UI hardens around them** — `agent/card.py` |
| 7.2 Answer card | `BOTH` | I build it; **you own whether it reads clearly** to someone who doesn't know the CBA. This is the demo. |
| All other 7.x | `CLAUDE` | Done. 7.4 found two engine defects (fixed) and one chat defect (open — build-plan 7.4, task 8.0) |

### Phase 8 — Ship

| Task | Owner | Notes |
|---|---|---|
| 8.0 Empty validation answer | `CLAUDE` | Done. Mean $0.12 a trade question, down from $0.24 (and empty two times in three); figures in build-plan 8.0 |
| 8.1 CI build pipeline | `CLAUDE` | PDF fetched by URL and checked by hash — D20 |
| 8.2–8.3 Vercel + Render deploys | `BOTH` | I write config, Dockerfile and CI; **you own the accounts, linking the repo, and the deploy** |
| 8.5 Secrets and spend cap | `YOU` | Platform env vars and the cap on the model key |
| 8.6 Always-on vs free tier | `YOU` | Settled: free tier (D21) |
| 8.4, 8.7 package + README | `CLAUDE` | 8.4 is GitHub-only (D22); name to settle |
| 8.8 Demo video | `YOU` | I can script it and pick the cases |
| 8.9 Write-up | `BOTH` | I can draft, but **it should sound like you** |

## 3. The CBA reading question

Task 2.1 says "read the CBA." Worth being precise about who does that, because it drives most of Phase 2.

**What I'll do:** write the parser (4.2) early — out of build-plan order, deliberately — and run it to get clean, section-numbered text. Then read the specific Articles and transcribe each rule into code with its citation constant attached. This is reading from source, not from memory, and it's the only acceptable way for me to write these rules.

A first raw extraction is already done (676 pages, ~1.37M characters, ~343k tokens), so this path is proven.

**Correction to an earlier claim.** I previously reported that this PDF's text layer has broken word boundaries throughout (`Generally Rec ognized`, `Tea m`, `w hose`) and that task 4.2 would need a normalization pass. **That was a pypdf artifact, not a property of the document.** Extracting with PyMuPDF yields zero occurrences of all seven defects tested, and runs 5x faster (1.4s vs 6.9s for the full document). No normalization pass is needed. Use PyMuPDF.

**The document also ships its own structure.** The PDF carries a 2,412-entry bookmark outline — 7 levels deep, covering pages 1–671 — that mirrors the legal hierarchy exactly: 42 Articles at level 1, 288 Sections at level 2, 938 subsections at level 3. `Article VII, Section 8. Trade Rules` resolves to p. 284 directly. Task 4.2 is therefore mostly outline traversal rather than heuristic parsing, which removes the largest piece of guesswork from Phase 4.

**What I need from you:** a verification pass on roughly fifteen load-bearing constants. Not the whole document — just the values where a transcription slip silently corrupts every downstream result:

- Salary matching percentages and dollar offsets (2.4)
- The full second-apron restriction list (2.7)
- Every hard cap trigger and which apron it sets (2.8)
- Designated veteran criteria (7.4)
- The trade date gates in 2.13

I'll produce these as a single table — value, Article, Section, page — so the check is a focused half hour against the PDF, not a re-read.

**Why I'm asking rather than just doing it:** I can transcribe accurately, but I can't independently confirm I've transcribed accurately. A second reader is the only real control, and these specific numbers propagate into every verdict the app ever gives.

---

## 4. How to hand me the data

**Don't pre-format it.** Give me whatever your collection process naturally produces — CSV, JSON, scraped HTML, a spreadsheet export with inconsistent columns. I'll write the importer. The first drop confirmed this works: the `NBA CBA data - *.csv` files load fine as-is, awkward column headers and all.

Drop files anywhere under `data/`. Useful if you can note, in any form: where each file came from and when you pulled it, anything you know is incomplete, and any player or team you had to guess on. That last one feeds 1.13 and 9.7 — the app should show its uncertainty rather than hide it.

### 4.1 What's left to collect

**Filled since the last pass:** years of service is now authoritative (`roster_experience.csv`, 661 players from Basketball-Reference's roster Exp column, replacing the `nbaDebut` approximation), and Chicago's Spotrac rows were recovered, taking that source to 30/30.

Three items remain, and the right answer for all three is **not to fill them**:

| Item | Availability | What to do |
|---|---|---|
| **Trade kickers** | No structured source. Spotrac's column is empty league-wide; one incidental mention across 814 Fanspo transactions. | Model as **unknown**, not zero. |
| **No-trade clauses** | No source. ~5 players league-wide qualify (8 years service, 4 with the team). | Model as **unknown**; hand-enter the handful if news confirms them. |
| **Cash considerations** | **Partly obtainable after all** — SalarySwish carries amount and direction ($1.25M MIL→ORL, $1.1M LAC→MIL). My earlier write-off was premature. | Ingest it. It matters directly: paying cash is row I of the Transaction Restrictions Table and sets a second-apron ceiling. Model as `unknown` only where absent. |

**Why unknown rather than zero.** Defaulting these to zero makes the engine quietly wrong: a trade that is actually illegal because of a 15% kicker would validate clean, with nothing anywhere indicating a guess was made. Task 5.7 already commits to stating assumptions rather than silently guessing, and 9.7 to showing provenance. These three are exactly that case.

The engine should carry a tri-state — present / absent / unknown — and a verdict touching an unknown should say so: *"Legal, assuming no trade bonus on [player] — not verifiable from available sources."* That is more useful than false precision, and it is a better story in the write-up than pretending to completeness.

Hand-entry stays available for any player where it matters enough to research, and the tri-state means partial coverage improves the answer without requiring completeness.

### 4.2 Birthdates and awards — verified against the PDF

Both are needed. The awards requirement is narrower than the obvious guess, so it's worth being exact.

**Birthdates — required.** Article VII, §3(a)(2), p. 222, the **Over 38 Rule**. Contracts covering seasons following a player's 38th birthday get special cap-allocation treatment. Needs the actual date, not the age. Narrow rule, but it changes cap figures, which changes trade math. Secondarily useful for aging assumptions in 6.5 and 8.1.

**Awards — required, but only three of them.** The governing term is **"Higher Max Criteria"** (Article II, §7, pp. 60–61):

> (A) the player was named to the All-NBA first, second, or third team, or was named Defensive Player of the Year, in the immediately preceding Season or in two (2) Seasons during the immediately preceding three (3) Seasons; or
> (B) the player was named NBA MVP during one of the immediately preceding three (3) Seasons

So collect: **All-NBA 1st / 2nd / 3rd team, Defensive Player of the Year, and MVP**, by player by season, for at least the last four seasons.

What it gates:

- **4 YOS** ("5th Year Eligible Players"): 25% of cap → up to 30%
- **8–9 YOS** with continuous-team tenure: Designated Veteran Player Contract, 30% → up to **35%**
- **Rookie scale extensions** have their own graduated table (Article II, ~pp. 65–66): All-NBA 2nd = 27%, All-NBA 1st = 28%, MVP = 30%

**All-Star selections are not part of the max criteria** — don't collect them for that purpose. They appear under a separate defined term, "Generally Recognized League Honors" (Article I(cc)), which bundles MVP, Finals MVP, DPOY, Sixth Man, Most Improved, All-NBA, All-Defensive, and All-Star. That term governs **incentive compensation** — whether a bonus is likely or unlikely, which flows into cap salary. Only collect the full honors set if we decide to model incentives, which I'd defer.

**Deferred:** award eligibility now carries a games-played requirement (§6, "Games Played Requirement for Certain League Honors" — 65 games, 20+ minutes counting as a game played, two exceptions at 15–20 minutes). Irrelevant for historical awards. Only matters if we ever *project* future eligibility, which needs games and minutes.

### 4.3 Collection priority

1. **Nothing is blocking.** Phases 0–4 and 7 can all proceed on what's in hand.
2. Run `spotrac_archive.py --year 2024` and `--year 2025` to size the historical picture before settling D6.
3. Years of service, if the extension-tier logic in 7.4 starts producing suspect results.
4. No-trade clauses and cash considerations — fill opportunistically.

## 5. What I can start on right now

Everything except Phases 5 and 6, which need the API key (B5).

- **Phase 0** — repo scaffold, toolchain, CI against `ankurbhatia28/nbacbaanalyzer`, ADR-001
- **Phase 1** — every type, against real data from four sources rather than a synthetic fixture
- **1.7's hard part** — 616 rows of draft-pick protection prose into structured predicates
- **Phase 2** — rules transcribed from the PDF with citations; 2.13 now has signing dates, so nothing is field-blocked
- **Phase 4.2** — the CBA parser, now mostly outline traversal (see §3)
- **Phase 7** — unblocked. Options, multi-year salaries, guarantee dates and extension-eligibility dates are all in hand.
- **Phase 3 scaffolding** — 814 transactions to normalize, pending D2

Suggested order: Phase 0 → Phase 1 → the 4.2 parser (out of build-plan order, since Phase 2 transcription wants clean section-numbered text) → Phase 2 → Phase 7.

## 6. Decisions — settled

| # | Decision | Outcome |
|---|---|---|
| D1 | Frontend | **Next.js + TypeScript** |
| D2 | Data sources | **Any reliable source.** Six scraped; see §1 inventory |
| D3 | Vector store | **Local** — SQLite FTS5 + on-disk embeddings, no hosted service |
| D4 | Tracing | **Raindrop, one trace per user session**, carrying user input, system prompt, every tool call and result, retrieved context, every intermediate model call, and the final output. Task 6.10. |
| D5 | Phase ordering | Superseded by the rescope — see `build-plan.md` |
| D6 | Historical scope | **Out of v1.** Current state only; historical questions are refused with a reason. Deferred to v2 item 11. |
| D7 | Model the 2017 CBA | **No** |
| D8 | Budget | **Local and minimal.** No *paid* hosted services in v1; hard spend cap on the model key (8.2). Free tiers on Vercel, Render and Raindrop are in scope — see D11 and D13 |
| D9 | Incentive compensation | **Out of v1** |
| D10 | Hypotheticals | **No.** "Is this legal" is answered; "should they do it" is declined. v2 may present live statistics alongside a trade but will not conclude. |
| D11 | Hosting | **Next.js → Vercel, FastAPI → Render.** Database and index are read-only build artifacts ([ADR-004](adr/0004-read-only-at-runtime.md)); no managed DB, no persistent disk. |
| D12 | Retrieval strategy | **BM25 for candidates, then term-coverage re-ranking** (SQLite FTS5, still no model at inference). Measured in 5.8: recall@1 34%, recall@3 48%, MRR 0.433 — but **76% recall@3 when the query carries the term of art against 20% when it does not.** Ranking work is done; the residue was vocabulary, settled by D14. |
| D14 | Paraphrase gap | **Resolve a question to one of the document's 670 names, then look the provision up** — not search for a paraphrase. Reaches 25 of 25 provisions the engine cites against 20% recall@3 by search. Exact matching only; an invented name resolves to nothing. Dense retrieval stays the fallback if 6.3's naming accuracy disappoints. See §6a. |
| D15 | Model per role | **Haiku 4.5 for routing; Sonnet 5 for provision-name selection and the answer.** (Intent moved up after 6.3 measured it — see §6b.) Not one model: ADR-001 leaves the model classification and selection, which do not need the top tier. Measured on the router (6.1): Haiku **88.9%** exact-set accuracy against Sonnet's 91.1%, both at **100% refusal recall**. 2.2 points is not worth the tier for a four-way label. Opus 5.5 held in reserve for the answer role if 6.11's adversarial set defeats Sonnet. Configured per role via `ANTHROPIC_MODEL_{ROUTER,INTENT,ANSWER}`; `ANTHROPIC_MODEL` pins all three, which is what an eval run does. See §6b. |
| D16 | Tracing vendor | **Langfuse Cloud Hobby.** Free, 50,000 units/month, 30 days retention. Self-hosting needs Postgres + Redis + ClickHouse + blob storage behind two containers, which contradicts D11 and buys only retention that `FileExporter` already provides. Supersedes the Raindrop half of D4 and D13. See §6c. |
| D17 | LLM gateway | **Not yet.** LiteLLM and OpenRouter both mishandle Anthropic's system-block `cache_control`, and 6.8 measured that caching cuts the answer role's billed input by 97%. A gateway's benefit is free model switching, which D15 settled by measurement instead. `llm.Caller` is a protocol, so the option stays one class away, and `Ledger.cache_hit_rate` is the canary. See §6d. |
| D18 | Current-season salaries | **Fanspo's payroll wins for the current season; Basketball-Reference for every later season and for options.** Settled 2026-10-03. Loading all 30 teams into the engine (7.0a) found Basketball-Reference's 2026-27 totals off Fanspo's by up to $39.4M (GSW), with 20 teams more than $5M apart, and the reconciler reporting 0 — salary never went through it. Fanspo is the source consistent with SalarySwish's hard caps: on Basketball-Reference figures MIN and PHI sat above their own first-apron ceilings, which cannot happen. B-R's current-season column reads as a projection (Draymond Green's $27.7M option year where Fanspo has a free-agent hold; camp minimums since released). Ingest now drops a B-R contract Fanspo's payroll does not list (111) and takes Fanspo's figure where both list one (42 differ), **recording every override as a disagreement**; Fanspo's dead cap is loaded (16 rows). Invariant test: no team's apron salary exceeds its own hard cap. Golden queries unchanged at 12/12. |
| D19 | Permalinks (7.7) | **The answer card travels in the URL.** Settled 2026-10-03. ADR-004 forbids runtime writes and D11 rules out a persistent disk, so a link cannot point at a stored answer. Re-running the question on open was rejected: it costs $0.01–0.13 per open and the answer can differ from the one shared. The card is compressed into the link with quote text dropped — quotes are re-fetched by citation, which is deterministic — so a link always shows exactly the answer that was given, for nothing. |
| D20 | CBA PDF in builds (8.1) | **Fetched from a stable URL and checked against a pinned sha256; never committed.** Settled 2026-10-05. NBA.com's copy (`ak-static.cms.nba.com/wp-content/uploads/sites/4/2023/06/2023-NBA-Collective-Bargaining-Agreement.pdf`) and the NBPA's (`imgix.cosmicjs.com/25da5eb0-…-Final-2023-NBA-Collective-Bargaining-Agreement-6-28-23.pdf`) were both byte-identical to the local file — 2,850,534 bytes, sha256 `bf178ca0f2d64f9dfe6fde095d3ae43d576b12e19ce7a679618d632584f7ab32`. **Rejected:** a private CI secret or artifact (opaque, for a file that is officially public), and committing the 4.5 MB index (breaks ADR-004's "out of git", and the index stops being derivable from source). Redistribution was not the deciding factor: the deployed app serves verbatim CBA text whichever way the index is built. What D20 buys is the reproducibility ADR-004 claimed but did not have — the index depended on a file that was not in source control. A changed or missing file fails the build loudly. |
| D21 | Render tier (8.6) | **Free tier; a ~30s cold start is accepted.** Settled 2026-10-05. Consistent with D8's no-recurring-fee constraint. |
| D22 | Engine package (8.4) | **Published on GitHub only, not PyPI, for now.** Settled 2026-10-05. Name to settle: the owner suggested `nba-cba-agent`; the engine imports no model client (ADR-001), so a name like `nba-cba-engine` may describe it more accurately. |
| D23 | Free models via OpenRouter | **Sonnet and Haiku stay the defaults; Nemotron 3 Ultra (free, via OpenRouter) is the fallback when the spend cap is reached, in place of refusing.** Settled 2026-10-05. Evaluated with the existing evals through a prototype OpenRouter caller (one run each): **Ultra** router 86.7% / refusal recall 100% / provision naming **84%** (Sonnet 80%) / adversarial **1 misleading in 30** (Sonnet: 1, twice) — quality-equivalent. **Rejected as the default anyway**: ~50s a question against ~10s, 503s on 3–30% of calls (all recovered on retry), and the free tier's 1,000 requests a day and 20 a minute come to roughly 200 questions a day and 4 a minute across all users, after which the app stops rather than costs more — to save perhaps $5–15 a month. **Nemotron 3 Super rejected outright**: refusal recall 85.7% (it answered a past-season question, D6), naming 64%. Free endpoints require allowing providers that may train on prompts. Reasoning models spend thinking out of `max_tokens`: at the router's 300 Super returned nothing, so an OpenRouter caller needs headroom. Ultra also exposed that a malformed tool argument crashed the request (fixed: `tools.call`). Qwen was the first pick and is not offered free; the third-party list that said so was wrong. Revisits D17 only for this fallback: caching does not matter on a free model. |
| D13 | Raindrop deployment (superseded by D16) | **Cloud, Hobby (free) tier** — event budget re-measured in 6.13a: **8–17 events per question, so ~60–125 questions a month**, not the ~140 first estimated. — there is no alternative: self-hosting is VPC-only, Enterprise, and in beta with selected partners. 1,000 events/month, 14-day retention, 1 custom signal. Pro is $299/month, which this project will not spend. **Narrows D8:** "no hosted services" already gave way to D11 (Vercel + Render); the operative constraint is no recurring fee, which the Hobby tier meets. |
| D24 | Off-topic questions (guardrail) | **Declined politely by the router, before any other model call.** Settled 2026-10-05. Scope is what the app can answer, not merely "is it about the NBA": contracts, payrolls, the salary cap, trades and the Agreement are in; other topics, and NBA games, scores, statistics and news, are out (basis `off_topic`, a third alongside D6 `historical` and D10 `opinion`). The reply says what the app *can* answer. An off-topic question costs one Haiku call (~$0.001) instead of a full answer. Router eval, 55 cases (ten added: six off-topic, four casual near misses that must not be refused): **92.7% twice, refusal recall 100%**; adversarial set 30/30 with **0 over-refused**. **Tried and removed:** a line saying awards and draft picks are on topic, to stop "Which players have won MVP?" and "Which draft picks have been forfeited?" being refused — both were already refused on `main` as *historical*, the line did not change that, and it is a D6 question, not a D24 one. |

## 6a. D14 — closing the paraphrase gap: **settled, option A**

Retrieval does well when a query carries the term of art (recall@3 76%, MRR
0.663) and poorly when it does not (20%). Task 5.8b exhausted what ranking can
do; what remained was that the user's words and the document's words differ —
§6(j)(4) says *aggregating* where a user says *combined*.

**Resolved as A: a question is resolved to a name and the provision is looked
up, rather than searched for as a paraphrase.** Dense retrieval (option C) is
not spent, so D8 and D11 are untouched and "no model at inference" still holds.

The implementation turned out stronger than the option was framed as. A in its
first form was "let the agent write a better search query", whose ceiling was
measured at **61.5% recall@3** even with the provision's own heading supplied —
not good enough. But a term of art does not need to be *searched* for. The
document names its own provisions, so the names can be indexed and resolved
exactly, which skips ranking altogether:

| | measured |
|---|---|
| vocabulary built from the document | **670 names** — 512 headings the drafters wrote, plus the defined terms |
| provisions the engine cites that are nameable | **25 of 25** (14 directly, 11 via the provision containing them) |
| deterministic lookup returns the target text | **25 of 25, 100%** (mean 7,927 characters) |
| the same questions, searched as paraphrases | 20% recall@3 |

Resolution is **exact on the normalised name**. Fuzzy matching would resolve
"traded player" to the Standard Traded Player Exception or to the definition of
a Traded Player depending on edit distance, and quietly citing the wrong
provision is the failure this project is arranged against. A name outside the
vocabulary gets no answer and the caller falls back to search.

**What Phase 6 now owes this** (task 6.3): pick a name from
`vocabulary_names()` — a closed set of the document's own words, not a free
-form guess — and the citation resolves deterministically from there. This does
not breach [ADR-001](adr/0001-the-model-does-not-decide.md): the model selects
which provision to *read*, it does not decide the rule or compute the figure,
and a name it invents resolves to nothing rather than to something plausible.

**Still unmeasurable offline:** whether a model picks the right name. That needs
Phase 6 and is 6.3's eval, not this one. What is settled is that the vocabulary
can reach every provision the engine cites, which is the bound that mattered.
Option C stays available if 6.3's naming accuracy disappoints.

## 6b. D15 — which model, and why not the expensive one

The agent is given very little to do. ADR-001 puts the reasoning in the engine:
nothing in `packages/agent` computes a figure or decides a rule. What is left is
classification, selection from closed sets, and restraint — so the question is
not "which model is best" but "which role needs what".

| role | the actual task | tier |
|---|---|---|
| `ROUTER` | sort a question into four classes plus a refusal | small — Haiku 4.5 |
| `INTENT` | pick from the document's 612 names (D14) | **mid — Sonnet 5**, moved up by 6.3 |
| `ANSWER` | orchestrate tools, quote provisions, surface assumptions | mid — Sonnet 5 |

**`INTENT` moved up, and the reason is partly counterintuitive.** Naming the right
provision reached 64% on the small tier against 80% on the mid tier — 16 points on
the task D14's whole retrieval strategy rests on. But the second reason decided it:
the prompt carries the document's 612-name vocabulary, about 3,150 tokens, which is
**above Sonnet's 1,024-token cache minimum and below Haiku's 4,096**. So it caches on
the larger model and not the smaller one. Uncached input across 25 calls: **609
tokens on Sonnet against 83,399 on Haiku.** The cheaper model is the one that resends
the prompt every time. Both minimums were measured by bisection rather than recalled.

**Measured, not assumed.** The router was scored on 45 labelled questions:

| model | exact-set accuracy | refusal recall | input tokens | output tokens |
|---|---|---|---|---|
| **Haiku 4.5** | **88.9%** | **100%** | 20,668 | 2,621 |
| Sonnet 5 | 91.1% | 100% | 27,302 | 3,502 |

Sonnet is 2.2 points better and costs more per token *and* used more tokens.
That is not worth a tier for a four-way label — particularly since **both reach
100% refusal recall**, which is the error that actually matters: a missed
refusal means a historical question gets answered from current data, and the
user cannot see that it is wrong.

`ANSWER` is the one role not on the small tier, because it is the only one where
the failure is a judgement failure rather than a wrong label — answering a
figure out of retrieved prose, or asserting a rule without calling a tool. Task
6.11 baits exactly that, and the tier for this role should be whatever passes
it. Opus 5.5 stays in reserve for that result, not for a preference.

**`.env.example` was pinning `claude-opus-5`** — the most expensive tier, and
not a current model id either. Now commented out so the per-role defaults apply.

**On caching, I guessed wrong and the measurement corrected me.** I expected 6.8
to reduce the router's 20,668 input tokens. It cannot: the router's prefix is 447
tokens, below the model's minimum cacheable length, so the breakpoint is silently
ignored (`cache_write=0`, `cache_read=0`, every call). Caching instead cuts the
**answer** role's billed input by **97%** — 8,262 uncached tokens become 252 —
which is the better place for it anyway, since that role runs on the mid tier and
carries the 2,697-token tool schemas. See 6.8 in the build plan.

## 6c. D16 — tracing vendor: **Langfuse Cloud Hobby** (settled)

Raised because the 6.13a measurement made the Raindrop free tier much tighter
than D13 assumed, and because Langfuse was worth checking.

| | Raindrop Hobby | Langfuse Cloud Hobby | Langfuse self-hosted |
|---|---|---|---|
| cost | free | free | free, open source |
| allowance | **1,000 events/mo** | **50,000 units/mo** | unlimited |
| retention | 14 days | 30 days | yours |
| self-host | Enterprise, VPC beta, selected partners | — | yes |

At the measured **8–21 events per question** (6.13a, 6.10) — *corrected below to 8–24 units*:

| | questions per month on the free tier |
|---|---|
| Raindrop | **~50–125** |
| Langfuse Cloud | **~2,100–6,250** (was ~2,400–6,250; see the correction below) |

That is the difference between a demo that runs out of tracing in a week and one
that does not. Self-hosting also removes the retention problem that 6.10a exists
to work around.

**Settled: Langfuse Cloud Hobby, and self-hosting is not worth it here.**

Self-hosting Langfuse needs **Postgres, Redis/Valkey, ClickHouse and blob
storage behind two containers** (Web and Worker). That contradicts D11 — "no
managed DB, no persistent disk" — and would not fit the free tier this project
deploys to. Six moving parts to run an observability stack, on a project whose
substance is the CBA reasoning.

And the one thing self-hosting buys is already covered. Its advantage over Cloud
Hobby is retention past 30 days; `FileExporter` keeps every trace locally for
nothing, and task 6.10a commits five of them to the repo. The durable record
exists either way.

50,000 units a month is roughly 2,100–6,250 questions at the measured 8–24
units each. We will not approach it.

**Correction, after Phase 7.0: a Langfuse unit is not a Raindrop event.**
Langfuse's pricing page defines a billable unit as "any tracing data point
sent to the platform -- including traces ..., observations (individual steps:
spans, events, and generations), and scores". The 8–21 above counted
observations only, so it missed the trace itself and its four scores: five
units on every question. Re-measured with `Trace.units` on the five committed
exemplars and a live run, **a refusal is 8 units and the heaviest data question
24**. The code had also kept Raindrop's 1,000-event cap (`max_trace_events`) and
its call-count estimate; both now count `Trace.units` against 50,000. The cap is
per process, not per calendar month, so it is a backstop rather than the bill.

`RAINDROP_API_KEY` in `.env` is now unused and can be removed. This supersedes
the Raindrop half of D4 and D13; the *shape* D4 specified is unchanged and
implemented.

## 6d. D17 — an LLM gateway (LiteLLM or OpenRouter): not yet, and the reason is caching

Both would work. Neither earns its place right now, and the blocker is specific.

**Prompt caching is doing a lot of work here.** 6.8 measured a 97% cut in the
answer role's billed input and a 100% hit rate on the intent role, whose prompt
carries 612 provision names. The breakpoint sits on the **system block**, which
is exactly the shape that travels worst through a gateway:

- LiteLLM supports *message-level* `cache_control` via injection points, not
  Anthropic's system-block parameter, and its OpenAI transport
  [strips `cache_control` from content blocks](https://github.com/BerriAI/litellm/issues/22071).
- OpenRouter caches Anthropic models only when explicit markers survive the
  route, and several reports describe routes
  [dropping them](https://github.com/anomalyco/opencode/issues/39009).

A gateway's main benefit is switching models freely. We do not need that: D15
settled the per-role assignment *by measurement*, and the one remaining
candidate is Opus for the answer role if 6.11 ever demands it.

**The option stays cheap.** `llm.Caller` is a protocol, so a LiteLLM or
OpenRouter client is one class implementing one method. And if we ever do switch,
the canary is already built: `Ledger.cache_hit_rate` would drop from ~100% to 0
and say so, rather than the bill quietly tripling.

**Revisit if** we want to evaluate non-Anthropic models side by side, or if cost
becomes dominated by something caching cannot reach.

## 7. The honest summary

I can write essentially all of the code. What I can't do is:

1. **Get the source documents and data** — done. The residue in §4.1 is small and blocks nothing.
2. **Independently verify my own transcription** of the numbers that matter most (§3)
3. **Supply basketball judgment** — need vectors, fit weights, strength priors (6.1, 6.5, 8.1)
4. **Touch anything requiring your accounts, credentials, or money** (0.4, 10.1, 10.2)
5. **Decide what to cut when something stalls** — especially 3.3

Items 2 and 3 are the ones that get skipped under time pressure, and they're the ones that determine whether the finished app is trustworthy or just plausible. Everything else is mechanical.


## Guarantee structure, trade kickers and no-trade clauses — sourcing (2026-09-30)

All three were listed as "model as unknown" for want of a source. One source covers
all three: **Hoops Rumors** publishes an annual article per topic, updated through the
season. `robots.txt` allows the article paths (it disallows only `/wp-admin/`,
`/search`, `/*/email` and some query strings) and declares `Crawl-delay: 1`, so this
fits the convention the existing scrapers already follow.

| gap | source | notes |
|---|---|---|
| Non-guaranteed and partial salary | [2026/27 non-guaranteed by team](https://www.hoopsrumors.com/2026/07/2026-27-non-guaranteed-contracts-by-team.html) | Partial amounts given to the dollar. Mostly Exhibit 10 deals plus ~40 real cases. League-wide guarantee date **January 10**. |
| Trade kickers | [2026/27 trade kickers](https://www.hoopsrumors.com/2026/08/nba-players-with-trade-kickers-in-2026-27.html) | Percentages given; most are 15%, the CBA maximum (Art. XXIV §2(a)(ii), p. 438). |
| No-trade clauses | [2026/27 players who can veto trades](https://www.hoopsrumors.com/2026/07/nba-players-who-can-veto-trades-in-2026-27.html) | Only **one** explicit NTC in 2026/27 (Lillard). The implicit ones are derivable, not scraped. |

### A derivation that did not work

Before looking for a source I tried to derive guarantee status from data already in
hand, since `contract_totals.csv` carries `guaranteed_remaining` (76% populated) and
`contracts.csv` carries per-season salary and option markers. Subtracting the
guaranteed total from the sum of listed seasons leaves a gap, and netting off the
option years should isolate non-guaranteed money. On 439 contracts that gave 331
"fully guaranteed", 30 "carrying non-guaranteed money", and 78 inconsistent.

Validated against the Hoops Rumors list, **only 2 of those 30 are really
non-guaranteed** (Moussa Cisse and Haywood Highsmith). The rest are false positives —
the derived set is topped by John Collins, Michael Porter Jr. and Isaiah Hartenstein,
none of whom appear on the authoritative list. `guaranteed_remaining` excludes more
than unexercised options, and the 78 inconsistent cases were the warning sign. **The
derivation is abandoned**; `guarantee_kind` stays `unknown` until the source above is
loaded.

### Priority note

Guarantee structure does **not** affect trade legality. Searching the CBA for
protection language inside the trade rules returns nothing: every occurrence sits in
the waiver and claim provisions (pp. 418–420). Salary matching uses a player's
*Salary*, not his guaranteed amount, so a non-guaranteed contract is traded at full
value. The gap therefore blocks waiver, stretch and roster-flexibility questions —
not 3.18 or 3.19.
