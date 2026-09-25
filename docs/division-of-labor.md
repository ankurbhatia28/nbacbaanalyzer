# Division of Labor

Companion to [`build-plan.md`](./build-plan.md). Task numbering matches that file exactly.

> **Status: data collection complete enough to build on.** Four sources scraped — Fanspo, Basketball-Reference contracts, Basketball-Reference awards, and archived Spotrac. Every numbered input is closed. What remains is three small items in §4.1, none of which blocks a phase. Scrapers and caveats: [`scraper/README.md`](../scraper/README.md).

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
| **Spotrac (archive)** | `spotrac_decisions`, `spotrac_roster`, `spotrac_cap_holds`, `spotrac_trade_exceptions` | 30/30 teams. Guarantee **dates**, extension-eligibility dates, qualifying offers, TPE original-vs-available. **Not** trade kickers (column empty league-wide) and effectively not incentives. Snapshot dates span 13 months — see `scraper/README.md`. |

Three sources independently cover draft picks, cap holds, trade exceptions and contract type. That redundancy is worth keeping — cross-source disagreement is a cheap correctness signal, and it already caught two real bugs (§1 caveats, and the option-signal gap in `scraper/README.md`).

## 2. Phase-by-phase ownership

### Phase 0 — Rails

| Task | Owner | What I need from you |
|---|---|---|
| 0.1 Monorepo scaffold | `CLAUDE` | — |
| 0.2 Toolchain | `CLAUDE` | — |
| 0.3 Lint + type gates | `CLAUDE` | — |
| 0.4 CI pipeline | `BOTH` | I write the workflow; you create the GitHub repo and confirm Actions is enabled |
| 0.5 LLM client module | `CLAUDE` | — |
| 0.6 Logging + tracing | `BOTH` | Decide: local structured logs only, or a hosted tracing tool (see D4) |
| 0.7 ADR-001 | `CLAUDE` | — |

### Phase 1 — Domain model

| Task | Owner | What I need from you |
|---|---|---|
| 1.1 `Season` | `CLAUDE` | Types now; values need B2 |
| 1.2 `Team` / `Player` | `CLAUDE` | — |
| 1.3 `Contract` | `CLAUDE` | **Unblocked** — 1,124 player-seasons with options; guarantee dates from Spotrac |
| 1.4 Contract type enum | `CLAUDE` | — |
| 1.5 `CapHold` | `CLAUDE` | Data in hand — `team_cap_hold.csv` |
| 1.6 `BirdRights` | `CLAUDE` | Data in hand — `rightType` on cap holds gives the classification directly |
| 1.7 `DraftPick` + protections | `CLAUDE` | **Unblocked** — 616 picks with full protection prose |
| 1.8 `TradeException` | `CLAUDE` | Data in hand, but see the two attribution/staleness caveats in §1 |
| 1.9 `TradeRestriction` | `CLAUDE` | — |
| 1.10 Roster state | `CLAUDE` | — |
| 1.11 Hand-built team fixture | `CLAUDE` | Synthetic, no real data needed. **Worth your review** — if the fixture misses an edge case, Phase 2 never tests for it. |
| 1.12 JSON Schema | `CLAUDE` | — |
| 1.13 Provenance fields | `CLAUDE` | Tell me your data sources so I can enumerate them |

### Phase 2 — Rules engine

This is where the split matters most.

| Task | Owner | What I need from you |
|---|---|---|
| 2.1 Read Articles I, VII, X | `BOTH` | **See §3.** Text already extracted; the ~15-constant verification pass is still yours. |
| 2.2 Three salary totals | `CLAUDE` | B1 |
| 2.3 Apron classification | `CLAUDE` | B1, B2 |
| 2.4 Salary matching bands | `BOTH` | I transcribe from the PDF; **you spot-check the numbers.** This is the most load-bearing constant in the codebase. |
| 2.5 Cap-space absorption | `CLAUDE` | B1 |
| 2.6 First apron restrictions | `CLAUDE` | B1 |
| 2.7 Second apron restrictions | `BOTH` | I implement; **you spot-check.** Second on the load-bearing list. |
| 2.8 Hard cap triggers | `BOTH` | I enumerate from the text; you sanity-check the list is complete against your own knowledge |
| 2.9 Stepien rule | `CLAUDE` | B1, B4 |
| 2.10 Base year compensation | `CLAUDE` | B1 |
| 2.11 Poison pill | `CLAUDE` | B1 |
| 2.12 Trade kickers | `CLAUDE` | B1 |
| 2.13 Trade date calendar | `CLAUDE` | **Unblocked** — 349 signing dates from `contract_notes.csv` |
| 2.14 Simultaneous vs. non-simultaneous | `CLAUDE` | B1 |
| 2.15 Multi-team trades | `CLAUDE` | B1 |
| 2.16 Roster + pick tradeability | `CLAUDE` | B1, B4 |
| 2.17 Violation → citation table | `BOTH` | I build it; **you audit it.** If a citation is wrong the app confidently misinforms people, and this is the one error type no test can catch. |
| 2.18 `validate_trade` API | `CLAUDE` | — |
| 2.19 Property-based tests | `CLAUDE` | — |
| 2.20 Golden tests from CBA examples | `CLAUDE` | B1 |

### Phase 3 — Ground-truth evals

| Task | Owner | What I need from you |
|---|---|---|
| 3.1 Scrape transaction log | `BOTH` | **Decision D2**: which source, and your call on its terms of service. I'll write the scraper for whichever you pick. |
| 3.2 Normalize into trade legs | `BOTH` | 814 records already scraped to start against. I do the bulk; ambiguous cases go to `data/evals/needs-review.jsonl` for you — expect 20–40, mostly multi-team deals and cash considerations. |
| 3.3 Reconstruct as-of-date state | `BOTH` | I build the reconstruction. **You decide the scope cut** if it stalls — see D6. Do not let me quietly expand this one. |
| 3.4 Assertion suite | `CLAUDE` | — |
| 3.5 Mutation generators | `CLAUDE` | — |
| 3.6 Precision/recall scoring | `CLAUDE` | — |
| 3.7 `make eval` + CI gate | `CLAUDE` | — |

### Phase 4 — CBA retrieval

| Task | Owner | What I need from you |
|---|---|---|
| 4.1 Acquire PDF | `YOU` | **Done** |
| 4.2 Structure-preserving parser | `CLAUDE` | — (see §3 on the word-boundary defect — this is now a known requirement, not a discovery) |
| 4.3 Chunking | `CLAUDE` | — |
| 4.4 Definitions handling | `CLAUDE` | — |
| 4.5 Cross-reference graph | `CLAUDE` | — |
| 4.6 Hybrid retrieval | `BOTH` | **Decision D3**: local embeddings vs. hosted vector DB |
| 4.7 Deterministic citation path | `CLAUDE` | — |
| 4.8 Golden Q&A set | `BOTH` | I draft ~50 questions with expected citations; **you review the expected answers.** A wrong gold label is worse than no eval — it makes a broken system look passing. |
| 4.9 Numeric guardrail | `CLAUDE` | — |

### Phase 5 — Agent layer

| Task | Owner | What I need from you |
|---|---|---|
| 5.1 Tool schemas | `CLAUDE` | — |
| 5.2 NL → trade legs + entity resolution | `CLAUDE` | — |
| 5.3 Structured outputs | `CLAUDE` | — |
| 5.4 Agent loop | `CLAUDE` | B5 |
| 5.5 Prompt caching | `CLAUDE` | — |
| 5.6 Streaming | `CLAUDE` | — |
| 5.7 Missing-data behavior | `CLAUDE` | — |
| 5.8 Adversarial eval | `BOTH` | I write the ~30 bait prompts; **add any you think of** — you know the phrasings a real fan would use better than I do |

### Phase 6 — Trade search

| Task | Owner | What I need from you |
|---|---|---|
| 6.1 Team need vector | `BOTH` | **Basketball judgment is yours.** What counts as a positional gap, how timeline is classified. I'll implement whatever you specify; I should not be inventing this. |
| 6.2 Archetype proposal | `CLAUDE` | — |
| 6.3 Staged pruning | `CLAUDE` | — |
| 6.4 Complexity control | `CLAUDE` | — |
| 6.5 Fit score | `BOTH` | Same as 6.1 — you set the weights, I build the machinery |
| 6.6 Mutual benefit constraint | `CLAUDE` | — |
| 6.7 Ranking + explanation | `CLAUDE` | — |

### Phase 7 — Cap sheet time machine

| Task | Owner | What I need from you |
|---|---|---|
| 7.1 Three-year projection | `CLAUDE` | Default growth assumption is yours to set |
| 7.2 Cap holds + renouncement | `CLAUDE` | — |
| 7.3 Options as branch points | `CLAUDE` | — |
| 7.4 Extension eligibility | `BOTH` | **Unblocked** — awards 2020-21→2025-26, plus extension-eligibility dates from Spotrac. I implement; **you spot-check** the designated-veteran criteria — intricate and easy to get subtly wrong |
| 7.5 Scenario tree UI | `CLAUDE` | — |
| 7.6 Threshold crossing flags | `CLAUDE` | — |

### Phase 8 — Protected pick simulation

| Task | Owner | What I need from you |
|---|---|---|
| 8.1 Win distribution | `BOTH` | You supply or approve the strength prior. Keep it simple — I'll push back if this starts growing. |
| 8.2 Standings simulation | `CLAUDE` | — |
| 8.3 Lottery draw | `CLAUDE` | — |
| 8.4 Protection resolution | `CLAUDE` | B4 |
| 8.5 Distribution output | `CLAUDE` | — |
| 8.6 Feed back into Stepien + search | `CLAUDE` | — |

### Phase 9 — Interface

| Task | Owner | What I need from you |
|---|---|---|
| 9.1 Trade builder | `CLAUDE` | — |
| 9.2 Violation panel | `BOTH` | I build it; **you own whether the plain-English explanations actually read clearly** to someone who doesn't know the CBA. This is the demo. |
| 9.3 Cap sheet table | `CLAUDE` | — |
| 9.4 Chat pane | `CLAUDE` | — |
| 9.5 Rumor check | `CLAUDE` | — |
| 9.6 Permalinks | `CLAUDE` | — |
| 9.7 Provenance display | `CLAUDE` | — |
| 9.8 States + mobile | `CLAUDE` | — |

### Phase 10 — Ship

| Task | Owner | What I need from you |
|---|---|---|
| 10.1 Deploy | `BOTH` | I write config and Dockerfiles; **you own the accounts, DNS, and the deploy button** |
| 10.2 Rate limit + spend cap | `BOTH` | I write the limiter; you set the cap on the key |
| 10.3 README | `CLAUDE` | — |
| 10.4 Demo video | `YOU` | Screen recording and narration. I can write the script and pick the trade to demo. |
| 10.5 Eval harness write-up | `BOTH` | I can draft it, but **this should sound like you** — it's the piece people will read as evidence of how you think |

---

## 3. The CBA reading question

Task 2.1 says "read the CBA." Worth being precise about who does that, because it drives most of Phase 2.

**What I'll do:** write the parser (4.2) early — out of build-plan order, deliberately — and run it to get clean, section-numbered text. Then read the specific Articles and transcribe each rule into code with its citation constant attached. This is reading from source, not from memory, and it's the only acceptable way for me to write these rules.

A first raw extraction is already done (676 pages, ~1.37M characters) and was used to verify the §4.2 data requirements, so this path is proven. **It also surfaced a defect worth knowing about now:** the PDF's text layer has broken word boundaries throughout — the document yields `Generally Rec ognized`, `Tea m`, `w hose`, `gr eater`, `de creases`. Left uncorrected this would split terms across chunk text and cause BM25 to miss a large share of query terms, producing retrieval scores that look mysteriously bad for no visible reason. Task 4.2 therefore needs a normalization pass before indexing. Better to have found it by accident now than to debug it in Phase 4.

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
| **Cash considerations** | Frequently never publicly disclosed. | Model as **unknown**. |

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
- **Phase 4.2** — the CBA parser, including the word-boundary normalization §3 describes
- **Phase 7** — unblocked. Options, multi-year salaries, guarantee dates and extension-eligibility dates are all in hand.
- **Phase 3 scaffolding** — 814 transactions to normalize, pending D2

Suggested order: Phase 0 → Phase 1 → the 4.2 parser (out of build-plan order, since Phase 2 transcription wants clean section-numbered text) → Phase 2 → Phase 7.

## 6. Decisions I need from you

Each has my recommendation. If you agree, say so and I'll proceed — no need to deliberate on any of them.

| # | Decision | My recommendation |
|---|---|---|
| D1 | Frontend stack | **Next.js + TypeScript.** Boring, well-supported, deploys trivially. |
| D2 | Transaction data source, and your ToS comfort | Your call — this is a legal judgment, not a technical one. Tell me the source and I'll write to it. |
| D3 | Vector store | **Local — SQLite FTS5 for BM25 plus an on-disk embedding index.** The CBA is one document; a hosted vector DB is unjustified infrastructure here, and local keeps the repo self-contained for anyone who clones it. |
| D4 | Tracing | **Structured local logs to start.** Add hosted tracing only if Phase 5 debugging gets painful. |
| D5 | Which of Phases 6/7/8 first | **Phase 7, the cap time machine.** It reuses Phases 1–2 most directly, needs no new data, and is the most genuinely useful of the three. Phase 8 next, since it feeds 2.9. Phase 6 last — it's the most work for the softest output. |
| D6 | Phase 3 fallback scope | **Deadline-day and offseason trades, 2023-24 forward.** Now live rather than hypothetical — the current data is a forward-looking snapshot with no historical state, so 3.3 needs either historical collection or this scope cut. Decide before Phase 3, not during it. |
| D7 | Model the 2017 CBA too? | **No.** It doubles the rules engine to extend the eval corpus backward. Not worth it. |
| D8 | Monthly LLM budget | Tell me a number and I'll build the spend cap around it. |
| D9 | Model incentive compensation? | **Not for v1.** It pulls in the full "Generally Recognized League Honors" set plus likely/unlikely bonus classification, for a modest accuracy gain on a minority of contracts. Revisit after Phase 7. |

---

## 7. The honest summary

I can write essentially all of the code. What I can't do is:

1. **Get the source documents and data** — done. The residue in §4.1 is small and blocks nothing.
2. **Independently verify my own transcription** of the numbers that matter most (§3)
3. **Supply basketball judgment** — need vectors, fit weights, strength priors (6.1, 6.5, 8.1)
4. **Touch anything requiring your accounts, credentials, or money** (0.4, 10.1, 10.2)
5. **Decide what to cut when something stalls** — especially 3.3

Items 2 and 3 are the ones that get skipped under time pressure, and they're the ones that determine whether the finished app is trustworthy or just plausible. Everything else is mechanical.
