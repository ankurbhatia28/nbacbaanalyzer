# Division of Labor

Companion to [`build-plan.md`](./build-plan.md). Task numbering matches that file exactly.

> **Status: Phase 0 complete, data collection done.** Scope is now CBA question answering, not trade analysis alone. Four sources scraped — Fanspo, Basketball-Reference contracts, Basketball-Reference awards, and archived Spotrac. Every numbered input is closed. What remains is three small items in §4.1, none of which blocks a phase. Scrapers and caveats: [`scraper/README.md`](../scraper/README.md).

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
| B5 | Anthropic API key | Still needed before Phase 5 |
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
| 6.10 Raindrop tracing | `BOTH` | I instrument; **you create the Raindrop account and provide the key** (Hobby tier, free — see D13). The Workshop MCP server failed to connect in this session, so I cannot verify traces land from here. |
| 6.11 Adversarial eval | `BOTH` | I write ~30 bait prompts; **add any phrasings a real fan would use** |
| 6.12 Cost tracking | `CLAUDE` | — |

### Phase 7 — Interface

| Task | Owner | Notes |
|---|---|---|
| 7.2 Answer card | `BOTH` | I build it; **you own whether it reads clearly** to someone who doesn't know the CBA. This is the demo. |
| All other 7.x | `CLAUDE` | — |

### Phase 8 — Ship

| Task | Owner | Notes |
|---|---|---|
| 8.1 CI build pipeline | `CLAUDE` | Emits `nbacba.db` and the index as deployment artifacts |
| 8.2–8.3 Vercel + Render deploys | `BOTH` | I write config, Dockerfile and CI; **you own the accounts, linking the repo, and the deploy** |
| 8.5 Secrets and spend cap | `YOU` | Platform env vars and the cap on the model key |
| 8.6 Always-on vs free tier | `YOU` | Render free spins down; a cold résumé link takes ~30s |
| 8.4, 8.7 package + README | `CLAUDE` | — |
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
| D13 | Raindrop deployment | **Cloud, Hobby (free) tier** — there is no alternative: self-hosting is VPC-only, Enterprise, and in beta with selected partners. 1,000 events/month, 14-day retention, 1 custom signal. Pro is $299/month, which this project will not spend. **Narrows D8:** "no hosted services" already gave way to D11 (Vercel + Render); the operative constraint is no recurring fee, which the Hobby tier meets. |
| D12 | Retrieval strategy | **BM25 first** (SQLite FTS5, no model at inference). Embeddings added only if the measured gain in 5.6 justifies the cold-start and bundle cost. Settled by measurement, not assertion. |

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
