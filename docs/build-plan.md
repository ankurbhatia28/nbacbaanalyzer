# Build plan

> ## Where this stands
>
> **Phases 0–7 are complete (last merge: PR #46, the trade builder, 2026-10-03). Phase 8 is under way: 8.0 and 8.1 are done (2026-10-05); the deploys, 8.2 and 8.3, are next — the API's image and Render Blueprint are written and tested, waiting on the owner's Render account.** The empty chat answer found in 7.4 is fixed — see 8.0 for the fix and the re-measured cost.
>
> | phase | state |
> |---|---|
> | 0 Rails · 1 Domain model · 2 Data layer · 3 Rules engine | done |
> | 4 Ground-truth evals · 5 CBA retrieval | done |
> | 6 Agent layer | done |
> | 7 Interface | done — chat, answer card, permalinks, cap sheet, trade builder |
> | 8 Ship | **in progress** — 8.0 and 8.1 done; read "Before starting Phase 8" below |
>
> **What the running app is**, for a session that was not here: `apps/web`
> (Next.js 16) has five pages — `/` chat, `/answer` a permalinked answer
> (7.7), `/cap` and `/cap/[team]` the cap sheet, `/trade` the trade builder. `apps/api` (FastAPI) serves `/health`,
> `/ask`, `/ask/stream`, `/quotes`, `/teams`, `/teams/{key}/sheet`, `/players`
> and `/trade`. Only the two ask routes call a model; the cap sheet, trade
> builder and quote re-fetch are deterministic. **The chat calls the rules
> engine for trades** (since 2026-10-05): the agent's `validate_trade` tool runs
> the trade builder's own check, so the two cannot disagree; the answer quotes
> each violation's provision and links to the builder.
>
> ### Before starting Phase 8
>
> Measured or checked on 2026-10-03; each bears on a task below.
>
> - **The artifacts are built in CI (8.1, done).** `python -m rag.fetch`
>   downloads the CBA PDF and refuses any copy that does not match the pinned
>   sha256 (D20); the `artifacts` job builds `nbacba.db` and `cba-index.db` and
>   uploads them as `nbacba-artifacts`. The deployed API needs only the index,
>   never the PDF. The index build is deterministic — same rows, same search
>   ranks — which D19's permalink quote hashes depend on; it is byte-identical
>   only on the same SQLite version (see 8.1).
> - **The API deploys as a Docker image (8.3).** The `Dockerfile` repeats the
>   fetch and both builds inside the image, so Render needs no CI artifact; the
>   runtime stage keeps the virtualenv, the package sources and the two
>   databases (83.5 MB), runs as a non-root user and cannot write to `build/`.
>   `render.yaml` deploys `main` only once CI passes, and CI's `image` job
>   builds it on every pull request.
> - **The in-app spend cap is not a monthly cap on Render (8.5).** `Budget`
>   counts in process memory, and the free tier restarts after every idle
>   spell, so the count resets many times a day. It still stops a runaway
>   burst. The monthly backstop is a spend limit on a dedicated Anthropic
>   Console workspace, whose key is the one Render gets.
> - **The artifacts are small and fast.** `nbacba.db` 532 KB in 0.3 s;
>   `cba-index.db` 4.5 MB in 2 s. Building them at deploy time costs nothing.
> - **Configuration is already environment-driven** (`.env.example` lists
>   all of it): `NBACBA_LEAGUE_DB`, `NBACBA_CBA_INDEX`, `NBACBA_ALLOWED_ORIGINS`
>   (CORS — unset outside development means *no* browser origin is allowed, so
>   the deploy fails closed until it is set to the Vercel URL),
>   `NBACBA_ENVIRONMENT`, the Anthropic key (**required at startup** — the API
>   refuses to start without it, by design, even though only chat uses it),
>   Langfuse keys. The web app reads
>   `NEXT_PUBLIC_API_URL` **at build time**, so changing the API's URL means
>   rebuilding the web app, not restarting it.
> - **Closed: the chat could get a trade verdict wrong.** After 8.0 one of nine
>   runs called Murray for Irving and Washington "legal in principle", where the
>   engine says illegal. The chat now runs `validate_trade` (see 7.4).
> - **The cold-start message is already written**: the web app tells the reader
>   a free-tier server can take about 30 seconds to wake (8.6).
> - Locally, `mypy` reports one error in `langfuse_export` that CI on `main`
>   does not; it is an environment difference, not a regression.
>
> Two items in Phase 3 are deliberately left open and say why inline: **3.14**
> (non-simultaneous TPE creation) and **3.16** (Art. VII §2(f), the Second Apron
> pick freeze).
>
> **Checkboxes in Phases 1–3 were stale until 2026-10-02** — the work was done
> during Phases 1–3 but never ticked, so this file read as though the domain
> model had not been started. Each was verified against the codebase before
> being ticked. If you are picking this up fresh, trust the boxes now, and
> re-run `gh pr list` before branching: the merge state lives on GitHub, not in
> this file.
>
> Decisions D1–D24 live in [`division-of-labor.md`](division-of-labor.md).
> The measured results worth knowing before changing anything:
> **router 88.9%** exact-set (6.1), **provision naming 80%** against a 100%
> ceiling (6.3), **retrieval recall@1 34%** (5.8), **adversarial 0–4 misleading
> failures in 30**, variance included (6.11), **97% of the answer role's input
> served from cache** (6.8).

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

- [x] **0.1** Monorepo: `packages/{engine,data,rag}`, `apps/{api,web}` — *ticked early: `apps/` did not exist until Phase 7. `apps/api` landed with 7.0; `apps/web` is still to come.*
- [x] **0.2** uv workspace, Python 3.12+
- [x] **0.3** ruff + mypy (strict on engine), pytest
- [x] **0.4** GitHub Actions CI against `ankurbhatia28/nbacbaanalyzer`
- [x] **0.5** CI + unit test enforce that `packages/engine` imports no LLM client
- [x] **0.6** ADR-001 (model does not decide), ADR-002 (query DSL), ADR-003 (unknown is not zero)
- [x] **0.7** `.env.example`, `.gitignore`, rescoped README

---

## Phase 1 — Domain model

*Every later phase reads these types. Mistakes here surface as unfixable bugs in Phase 3.*

- [x] **1.1** `Season` — cap, tax, both aprons, three MLE tiers, BAE, minimum scale by YOS, rookie scale by slot
- [x] **1.2** `Team`, `Player` — including authoritative years of service from `roster_experience.csv`
- [x] **1.3** `Contract` as a row per season — cap figure, guarantee status and date, option type, incentives, trade kicker, no-trade clause
- [x] **1.4** Contract type enum — rookie scale, veteran, max, minimum, two-way, Exhibit 10
- [x] **1.5** `CapHold` — free agent holds, roster charges, unsigned pick holds
- [x] **1.6** `BirdRights` — Full / Early / Non, from `team_cap_hold.rightType`
- [x] **1.7** `DraftPick` — protection as a structured predicate plus conveyance rule; swaps as their own entity
- [x] **1.8** `TradeException` — amount, created, expiry, and apron-dependent usability
- [x] **1.9** `TradeRestriction` — reason and expiry, so violations can explain themselves
- [x] **1.10** Roster state — 15 standard, 3 two-way, 14 minimum with grace
- [x] **1.11** **`Unknown` as a first-class type.** Tri-state present / absent / unknown for trade kickers, no-trade clauses, cash. Never coerced to zero — [ADR-003](adr/0003-unknown-is-not-zero.md)
- [x] **1.12** Hand-built fixture team covering every edge case, before real data
- [x] **1.13** JSON Schema for the whole model — one contract shared by engine, API, web, and evals
- [x] **1.14** `as_of` and provenance on every ingested record
- [x] **1.15** **Apron *status* and apron *ceiling* are separate fields.** Status is where a team's Apron Team Salary sits. Ceiling is what a prior transaction forbids it from exceeding. Houston is far *below* the second apron yet may not cross it; OKC is far *above* it and may go higher. A single "apron" field conflates opposite situations.
- [x] **1.16** **`HardCapCeiling` is a set, not a scalar.** One entry per triggering transaction — `(trigger_row, apron_level, effective_date, source_transaction)` — with the operative ceiling computed as the **minimum**. Confirmed against real data: Milwaukee holds a first-apron ceiling (Jul 8 expanded-TPE acquisition) *and* a second-apron ceiling (Jun 24 cash payment); trackers show 1st because the lower one binds.

> **Done when** a full 30-team league state loads from the scraper CSVs, round-trips through the schema, and any team's roster and contract detail is queryable.

---

## Phase 2 — Data layer

*New in this scope. Data questions are a first-class surface, so the dataset needs to be queryable — safely.*

- [x] **2.1** SQLite schema derived from the Phase 1 model
- [x] **2.2** Ingest the six sources with explicit precedence rules per field — *current-season salaries changed to Fanspo in Phase 7 (D18), with every override reported*
- [x] **2.3** Cross-source reconciliation and a disagreement report
- [x] **2.4** Entity resolution across sources — `bbref_id`, Fanspo `playerId`, Spotrac display names
- [x] **2.5** Query DSL schema — entity, filters, grouping, aggregation ([ADR-002](adr/0002-structured-query-not-text-to-sql.md))
- [x] **2.6** Deterministic DSL → SQL compiler
- [x] **2.7** Validation with errors written for a model to act on, one bounded retry
- [x] **2.8** Golden query tests — question → DSL → expected rows
- [x] **2.9** `player_lookup` fuzzy search returning candidates, never a guess
- [x] **2.10** Refuse what the DSL cannot express; log each refusal as a candidate extension
- [x] **2.11** **`guarantee_kind` now reads `unknown`, not `full`.** The schema defaulted it to `'full'` and the loader wrote `'full'` positionally, so all 1,136 contract-years claimed to be fully guaranteed — while the scraped CSV has no guarantee column at all. Basketball-Reference marks guarantee status with cell styling the scraper never read, so the value was asserted, not observed, in breach of [ADR-003](adr/0003-unknown-is-not-zero.md). The catalog advertised "full, partial or none" on a column that could only ever say one of them. Found by writing the 4.7 question "which contracts are not fully guaranteed?", which returned an empty list — readable as "none", which was false. Closing it properly needs a source that publishes guarantee dates and amounts.

> **Done when** "how many players have Bird rights this season" returns a number, the DSL behind it is inspectable, and an unexpressible question is refused rather than approximated.

**Why not text-to-SQL:** a generated query that joins wrong produces a plausible number with no error anywhere — the same invisible failure as letting the model do arithmetic.

---

## Phase 3 — Rules engine

*Pure functions over Phase 1 types. No model calls — enforced by lint and CI.*

- [x] **3.1** Read Articles I, VII, VIII and X from the PDF, taking section references as you go
- [x] **3.2** Three salary totals — cap, tax, apron. They diverge on holds and exceptions. — *Corrected in Phase 7: `apron_team_salary()` was a placeholder equal to cap salary, which counted every cap hold toward the aprons. Art. VII §2(e)(1) subtracts Free Agent Amounts (iv), unsigned first-round picks (vi) and incomplete-roster amounts (x), and adds a restricted free agent's qualifying offer (v). The Denver worked example had encoded the error: $41.9M of holds made a $208.7M taxpayer read as a second-apron team. Room is now judged on cap salary, holds included.*
- [x] **3.3** Apron classification — room / over-cap / taxpayer / first apron / second apron
- [x] **3.4** Salary matching bands — transcribed from the text, never from a summary
- [x] **3.5** Cap-space absorption path for room teams
- [x] **3.6** First apron restrictions — **derived, not transcribed.** The CBA has no such list; the restrictions fall out of Art. VII §2(e)(2)(i)(A) — a team may not use a Transaction Restrictions Table row if it would exceed that row's level immediately after. Rows A–F close above the first apron.
- [x] **3.7** Second apron restrictions — aggregation, prior-year TPEs, cash, taxpayer MLE, frozen pick
- [x] **3.8** Hard cap ceilings. The CBA never says "hard cap" — the mechanism is Art. VII §2(e)(2)(i)(B), driven by the **Transaction Restrictions Table** (§2(e)(4), pp. 214–215), **rows A–K**. Encode all eleven: A–G set the **first** apron (bi-annual exception, non-taxpayer MLE, sign-and-trade acquisition, waived-player signing above the MLE, expanded TPE, post-season standard TPE, transition TPE); H–K set the **second** (aggregated TPE, **paying cash in a trade**, TPE from a signed-and-traded contract, taxpayer MLE). §2(e)(2)(ii) makes rows E–J executed after the Regular Season bind the *following* Salary Cap Year.
- [x] **3.9** Stepien rule — **implemented from the NBA Constitution and By-Laws §7.03** (p. 85), where it is unnamed. No provision restricts assigning draft picks between teams; the rule lives in the NBA Constitution and By-Laws, which p. 322 explicitly holds separate ("nothing contained in this Agreement shall be deemed to be an agreement of the Players Association to any provision of the NBA Constitution and By-Laws"). Two prohibitions: no selling first-round pick rights for cash, and no trade whose result *may be* to leave a Member without first-round picks in any two consecutive future Drafts. Cited as a By-Law, not a CBA provision, since the documents have different force.
- [x] **3.10** ~~Base year compensation~~ — **eliminated.** "Base Year" appears **zero** times in 676 pages. The term is definitional, so its absence is conclusive rather than suggestive. The rule does not exist under the 2023 CBA.
- [x] **3.11** Poison pill — **located and implemented.** The nickname covers two provisions sharing one mechanism: Art. VII **§8(g)** (Rookie Extension Trade Rule, pp. 288–289) and Art. XI **§5(d)** (Gilbert Arenas, pp. 346–347). Both deem a salary to equal the average of a contract's remaining years, for one party's Room only. I had searched §7 (Extensions); the trade-valuation rule lives in §8 (Trade Rules).
- [x] **3.12** Trade kickers — honouring `Unknown` rather than assuming zero. **Source found:** Hoops Rumors publishes an annual list with percentages ([2026/27](https://www.hoopsrumors.com/2026/08/nba-players-with-trade-kickers-in-2026-27.html)). **Settled:** the **sending** team pays the player (Art. XXIV §2(a), p. 438), but the bonus lands in the **acquiring** team's Team Salary and counts as incoming trade salary for matching — so the engine's existing treatment was right. Teams may alter the payment arrangement between themselves, governed by cash-in-trade (Art. VII §8(a)), which does not move the cap hit. **A player may also reduce or waive the bonus** (§2(a)(iii)(B)(3), p. 439), so a deal failing *only* on a kicker is conditional, not illegal — the constraint report now says so instead of marking it blocking. Keyword search did not surface a single clause stating the acquiring-team attribution; it is recorded on the user's domain knowledge, consistent with §2(a) and p. 295.
- [x] **3.13** Trade date calendar — Art. VII §8(c)–(d). Four rules with separate clocks: no trade after the deadline in a possible final Season; 30 days for rookies and two-ways; later of 3 months or **December 15** for free agent signings; later of 3 months or **January 15** for a prior-team re-signing above **120%**. The last bars the *trade*, not merely aggregation — distinct from the two-month bar in §6(j)(4)(i).
- [x] **3.14a** **Structuring across several exceptions.** Art. VII §6(j)(1)(i) lets one exception replace "one (1) Traded Player", and §6(m) carves §6(j) out of its bar on combining Exceptions — so a team sending several players may use several. Modelling a trade as a single exception understated capacity: four contracts totalling $47.4M permit **$81.1M structured vs $59.5M** as one exception. `best_structure()` enumerates the partitions. Found by the eval harness, not by reading — 14 of 20 undetermined legs acquired two or more players.
- [ ] **3.14** Simultaneous vs non-simultaneous trades and TPE creation. **Partial:** 3.14a built structuring across several simultaneous exceptions; creating a *non-simultaneous* TPE from a trade is not implemented.
- [x] **3.15** Multi-team trades — validate each team's send and receive independently
- [ ] **3.16** Roster counts and pick tradeability. **Partial:** roster counts and By-Law 7.03 pick tradeability are built and used by 3.19; **Art. VII §2(f)** (the Second Apron pick freeze) has a citation but no implementation, and the seven-Drafts-ahead horizon is unsourced (`constitution.PICK_HORIZON_NOT_SOURCED`).
- [x] **3.17** **Violation code → CBA citation table.** The join between engine and retrieval; the reason citations are right
- [x] **3.18** `validate_trade(legs, as_of) -> Verdict` with violations **and assumptions**
- [x] **3.19** **`team_trade_constraints(team, player) -> Constraints`** — enumerate everything limiting a team, without a proposed deal. Answers the Embiid question. **Built.** Hard-cap ceilings (binding and superseded), player-level restrictions, trade kickers, and now:
  - **the Transaction Restrictions Table rows the team may not engage in** — the substance of the answer, since being over an apron does not stop a team trading, it stops it trading in particular *ways*
  - **first-round pick tradeability, asked one pick at a time.** A team can be free to move one year's first and barred from moving another's, so a single yes/no over the inventory would be wrong. On the real Clippers position (firsts in 2027/29/31/33, bare in 2028/30/32) every held first is untradeable while the position itself is legal
  - trade-date windows, with the flags we lack recorded as assumptions — a bar not evaluated reads as "tradeable"
  - the roster minimum and maximum, which shape how a deal may be built
  - **take-back capacity in dollars** via `best_structure` — a list of prohibitions is not the whole answer
  - no-trade clauses, tri-state: unknown is surfaced, absent stays quiet

  Two fixes fell out of it: `RestrictionRow.describe()` (the rows had no human-readable phrasing, so prohibitions would have rendered empty), and a **miscitation** — `TransactionPermission` cited §2(e)(2)(i)(**B**), the ceiling that attaches *after* a permitted transaction, for a rule that implements (i)(**A**), the prohibition itself. Added `TRANSACTION_PROHIBITION` with the verbatim text from p. 211.

  Still absent rather than approximated: Art. VII §2(f) (the Second Apron pick freeze, **not implemented** despite a citation existing for it) and the seven-Drafts-ahead horizon.
- [x] **3.20** Every verdict carries the assumptions it rests on (ADR-003)
- [x] **3.21** Property-based tests — invariants across the input space: permission is monotonic in salary, expanded is never worse than standard, a returned allowance always fits, more ceilings only tighten, more lost picks never make Stepien pass, an unknown always records exactly one assumption.
- [x] **3.22** Golden tests from the CBA's own worked examples

> **Done when** the fixture team validates correctly, every rule has a citation constant and a test, and `team_trade_constraints` explains a real team's situation in terms traceable to Articles.

---

## Phase 4 — Ground-truth evals

*Every completed trade was legal when it happened. Hundreds of free, self-labelling cases.*

- [x] **4.1** Corpus built from **SalarySwish** rather than Fanspo. Fanspo yielded 62 trade events across 9 months; SalarySwish gives **184 trades across four seasons** (2023-07 → 2026-09), all under the 2023 CBA.
- [x] **4.2** Legs derived from two published figures per team: `incoming = Cap Hit Sum`, `outgoing = Cap Hit Sum − Cap Hit Change`. Verified rather than assumed — **all 184 trades balance**, total incoming equalling total outgoing.
- [x] **4.3** Scope note: v1 validates against **current-state** reconstruction only. Trades needing state we lack are excluded and counted, not silently skipped.
- [x] **4.4** **184/184 trades, zero failures.** 344 salary-matching checks pass; 75 are undeterminable and skipped, as are 161 ceiling checks. Partial verdicts throughout: a skipped check says why.
- [x] **4.5** Mutation generators — **633 mutants** from real trades. Three kinds: blunt inflation, **boundary mutations set one dollar above the largest allowance any lawful *structure* offers** — not merely any single exception, which was letting still-legal trades count as illegal — and unbalancing, which tests the harness rather than the engine.
- [x] **4.6** **Recall 100%** (633/633), **reason accuracy 100%**, **precision floor 97.4%**. Precision is reported as a floor, not a measurement: its denominator counts real trades the engine cannot permit outright, most of which are cap room rather than errors.
- [x] **4.7** Query DSL eval set — **18 golden questions**, 12 answerable by one query and all 12 correct. The other 6 are labelled with the category that should route them elsewhere (rules, validation, constraints, refused), which is what task 6.1 will be measured against. Graded **on the result, not the query text**: an alias, a different column order or a different filter order is still a correct translation. A real data defect fell out of writing it — see 2.11.
- [x] **4.8** `python -m nbadata.evals` prints the report card and **the CI job is now blocking** — a regression in the suite fails the build.

> **Done when** you can state "passes N/N reconstructible trades, M% violation-code accuracy" and defend how it was measured.

---

## Phase 5 — CBA retrieval

- [x] **5.1** Extract with **PyMuPDF**, not pypdf — zero word-boundary defects, ~5× faster. All PyMuPDF access is confined to one function, since it ships no type information and every call needs an escape hatch.
- [x] **5.2** Unit tree built from the PDF's own **2,412-entry bookmark outline** — **2,411 units placed**, 42 Articles confirmed. The one failure has a malformed bookmark title (words run together, unsearchable); it is reported on `Outline.unmatched`, never dropped.

  Three things the outline does not hand over for free:
  - **Locating text.** The outline gives a page, not an offset, and every definition in Art. I §1 starts on page 25. Entries are found by searching from their own page, so the Table of Contents — which repeats every heading verbatim — cannot match first. Titles are truncated at 254 characters, so matching uses a normalised 40-character prefix: **2,411 of 2,412 match, against 1,069 for the full title**.
  - **Numbering.** One bookmark can carry two levels: the entry for §2(e)(2)(i) is titled `"(2) (i) At any point..."`. Worse, the outline then puts `(A)` and `(ii)` at the same depth below it — although `(A)` is a *child* of `(i)` and `(ii)` is its *sibling*. Depth cannot tell them apart; the **marker series** can. A marker that is the successor of the parent's trailing marker continues the series, so it is a sibling. This also dissolves the letter-vs-roman ambiguity without resolving it: the first marker of any series is never a successor, so `(i)` after `(d)` opens the romans while `(i)` after `(h)` continues the letters.
  - **Page numbers.** The pages carry a printed folio running **24 behind the PDF page** (PDF 25 is printed page 1), confirmed on 560 of the 563 machine-readable folios. Both are kept on every unit, because "p. 211" is otherwise ambiguous — `engine.citations` values are PDF pages.
- [x] **5.2a** **The outline cross-checks the engine's citation table, and found four errors.** Every one of the 30 citations now resolves and points inside its own provision's page span:
  - `APRON_LEVELS` cited **§2(e)(1)(iii)**, which is part of the *Apron Team Salary computation*. The levels are defined at **§2(a)(4)(iii)** (pp. 195–197) — *"a 'First Apron Level' and a 'Second Apron Level' as follows"*. Wrong provision, right page.
  - `NON_TAXPAYER_MLE` cited p. 262; §6(e) runs **pp. 260–261**, and p. 262 is already §6(f) and §6(g).
  - `ARENAS_OFFER_SHEET_LIMIT` p. 346 → **347**; `GENERALLY_RECOGNIZED_HONORS` p. 27 → **28**.

  Asserted as "the cited page falls inside the provision's span" rather than "equals its first page", because a provision regularly runs across a page break and pointing at the sentence that matters is legitimate. A parametrised test now holds all 30, so the table cannot drift from the document again.
- [x] **5.2b** **Ancestor fallback for unbookmarked provisions.** The PDF has no bookmark for Art. VII **§8(e)**, the sign-and-trade rule the engine enforces. `resolve()` returns the containing Section together with *the citation it actually reached*, so a caller can say "Art. VII §8" rather than claiming to quote §8(e)(1).
- [x] **5.3** **Retrieval units: 1,276 chunks, median 592 characters, p90 2,320.** A Section is what a lawyer cites and for most of the document it is also the right size — the median Section is ~1,500 characters. But the tail is long (Art. VII §1 Definitions is **82,893** characters, §2 is 52,436), so Sections are opened into their subsections recursively wherever they exceed the ceiling.

  The split follows the document's numbering rather than a character window, so every chunk keeps a checkable citation and none begins mid-provision. **Lossless**: Art. VII §6 is 39,262 characters in and 39,262 across 38 chunks out, asserted as a test on the four Sections that actually split.

  A parent's **preamble is kept** when its children are split out — §6(j) opens *"Subject to the rules set forth in Section 2(e) above"*, and dropping it would strip the apron precondition off every exception beneath it. Only **2** units exceed the ceiling with nothing left to split on, and both are flagged rather than force-cut: `Art. XI §5(j)(ii)(1)`, and `Art. XLII §3` (Exhibits), whose contents the PDF bookmarks as top-level entries rather than children of the Section.

  `MAX_CHARS = 4000` is a starting point, not a finding — per D12 it gets chosen against recall@k in 5.8 rather than asserted here.
- [x] **5.4** **Definitions index — 162 definitions, 176 names including aliases and pointers.** Article I opens *"As used in this Agreement, the following terms shall have the following meanings"*, and those meanings govern every other Article. A passage read without them supports a confident wrong answer.

  - **Definitions are not only in the Definitions sections.** Three Sections are titled that (Art. I §1 with 87 terms, Art. VII §1, Art. XXXIII §1), but terms are also defined where they are needed — "Force Majeure Event" sits alone at Art. XXXIX §5(a). Every unit is scanned, not just the titled ones.
  - **Four alias shapes, all of which the first parser missed:** an "or" alias (`"Audit Report" or "final Audit Report"`), a parenthetical (`"Early Termination Option" (or "ETO")`), a bare cross-reference (`"Player Contract" (see "Uniform Player Contract")`), and a comma-separated list inside the quotes (`"Renegotiation," "renegotiate," or "renegotiated"`). Plus the `The term "negotiate" means` lead-in.
  - **Matching is case-sensitive**, because the document's convention is that a term is Capitalised where it carries its defined meaning. "the player" is not "the Player", and conflating them attaches a definition to every ordinary use of the word.
  - **Nested terms resolve to the longest.** "Apron Team Salary" contains "Team Salary" and "Salary", both separately defined; reporting the generic one would label a passage with a term it does not use. A genuinely separate later occurrence still counts.
  - **Ubiquitous terms are suppressed** rather than ranked down — "Team", "Agreement", "Salary Cap Year" match constantly and explain nothing, and every slot they take is one the operative term does not get. Held as an explicit list so it can be argued with; a test enforces that every entry is a name the document actually defines, after an earlier version listed "Player" and "NBA", neither of which the CBA defines at all.
- [x] **5.5** **Cross-reference graph — 1,217 edges from 833 provisions, 20 unresolved (1.6%).** The CBA is a network, not a list: Art. VII §6(j)(1)(i) opens *"Subject to the rules set forth in Section 2(e) above"*, and §2(e) is where the apron restrictions live. Retrieving the exception without that reference returns a permission stripped of its precondition.

  - **Resolution is per unit, because context decides the target.** A bare "Section 6(j)" means Section 6(j) *of the Article it appears in*; the same string in two Articles points at two different provisions. The text makes 1,144 bare references against 337 that name their Article.
  - **Statutory references are excluded.** Article IV cites the Internal Revenue Code constantly — "Section 401(a) of the Code", "Section 415(d)(2) of the Code" — and Article VI cites "Section 302(c)(5) of the Labor Management Relations Act of 1947". Read as internal references these produced 33 edges to provisions that do not exist, which is how they were found: every one failed to resolve. Excluding them took unresolved references from 53 to 20.
  - **Unresolved references are kept, not dropped.** An edge to a provision that does not exist would send retrieval after nothing, but discarding the reference would hide that the parser and the outline disagreed. They sit on `Graph.unresolved`.
  - **One hop by default.** Two hops reaches most of Article VII from almost anywhere inside it, which stops being context and becomes the whole Article. Seeds are returned first so a caller can tell them from an expansion, and the reverse direction (`cited_by`) answers what relies on a provision.
- [x] **5.6** **BM25 over SQLite FTS5 — 1,276 chunks in a 5.0MB artifact, no model at inference.** External-content FTS5, so the index points at the chunk table rather than holding a second copy of 1.2MB of text. `python -m rag` builds it and reports what went in.

  **The trap worth naming:** FTS5 treats parentheses as grouping, so *"what does 6(j) say"* is not a query that returns nothing — unescaped it is a **syntax error**. Every query goes through `escape_query`, which strips operators and quotes each term; passing user text to MATCH is the same class of mistake as string-building SQL. Tested against parentheses, quotes, bare `AND`/`NOT`, wildcards, `NEAR`, empty input and stop-words-only.

  `OR` beats `AND` as the default, measured rather than assumed: their top-3 agree where both work, but `AND` returns **nothing** for "Bird rights qualifying veteran" since no single passage carries all four terms.

  **The artifact is self-contained** (ADR-004): definitions and cross-reference edges are written into it, so the serving application never parses a 676-page PDF at startup. Opened read-only — a test asserts a write fails.

  26 citations cover more than one passage (Art. VII §2(e) carries its heading plus five worked Examples, one of which established that §2(e)(5) reaches the (i)(A) prohibition). They stay separate because they are separately useful, and carry an ordinal so two results are never both labelled "Art. VII §2(e)".
- [x] **5.7** **Deterministic citation path — all 30 engine citations reach substantive text.** No ranking, no model, nothing that can return the wrong provision because a query was phrased oddly.

  Getting there needed two corrections, both found by checking the whole citation table rather than a sample:
  - **String-prefix fallback is not good enough.** §2(e)(2)(ii) shares a prefix with §2(e), whose own chunk is the 30-character heading *"(e) Operation of Apron Levels."* — so the walk "succeeded" while returning nothing quotable. Citations are now mapped to the **smallest chunk whose text contains them**, computed by span at build time (2,285 rows).
  - **A Section-level citation resolves to its preamble**, which is frequently just a title — *"Section 8. Trade Rules."* is 23 characters. Those now bring their subsections too.

  Asserted on **total characters, not "a passage came back"**: a lookup returning 23 characters of heading reports success and conveys nothing. Where a citation is finer than any chunk (§2(e)(2)(i)(A) lives inside §2(e)(2)(i)), the substitution is reported on `resolved_to` so a caller never claims to quote (A) while holding (i). An unknown citation returns nothing rather than a near miss.

  **Provenance on every passage:** matched the query, referenced by something that did, or fetched by citation. Context is not evidence — an answer resting only on expansion means the query never matched the provision it claims to rely on. Expansion is capped at 2 per hit and 4 overall, because the Transaction Restrictions Table alone cites eight provisions and one broad match would otherwise bury the passages that answered the question.
- [x] **5.8** **Golden Q&A set — 50 questions. `python -m rag.eval_cli` scores it.** After the ranking fix in 5.8b: **recall@1 34%, recall@3 48%, recall@10 66%, MRR 0.433.**

  **Where the expectations come from matters more than how many there are.** Writing both the question and its answer invites a set that flatters whatever the retriever already does, so none are chosen freely: the 25 rules questions take their citations from the engine's table, which 5.2a verified provision by provision, and the 25 definition questions read theirs out of the built index, so they cannot drift from what the parser extracted. Questions are phrased as a user would ask, not in the provision's words.

  **The split is the finding, and the aggregate hides it:**

  | phrasing | n | r@1 | r@3 | r@10 | MRR |
  |---|---|---|---|---|---|
  | paraphrased, no term of art | 25 | 12.0% | 20.0% | 48.0% | 0.202 |
  | contains the term of art | 25 | 56.0% | 76.0% | 84.0% | 0.663 |

  **Retrieval is now good when the query carries the term of art and still poor when it does not.** That is the live constraint on Phase 6, and it is a vocabulary problem, not a ranking one.

  **Scoring credits containment, not string equality.** A question about §6(j)(1)(i) is answered by the chunk for §6(j)(1), which contains it. Demanding an exact match would mark right answers wrong and make the score an artefact of the chunk ceiling. Scored on **search alone** — expansion and definition attachment make an answer more useful but would make it impossible to tell whether the query found the provision or merely found something pointing at it.

  Two harness faults it surfaced, both now tested against: `Art. VII §8(e)(1)` is unreachable because the PDF never bookmarks §8(e) (5.2b), so that question targets the containing Section; and "Tax Level" was in the term list although the document quotes it once and never defines it.

- [x] **5.8a** **The chunk ceiling is measured, not guessed.** `MAX_CHARS` was 4,000 by assertion; swept against the golden set it settles at **6,000**, re-confirmed after the ranking change.

  | ceiling | r@1 | r@3 | r@10 | MRR |
  |---|---|---|---|---|
  | 1,000 | 32.0% | 42.0% | 50.0% | 0.380 |
  | 4,000 | 34.0% | 44.0% | 62.0% | 0.422 |
  | **6,000** | **34.0%** | **48.0%** | **66.0%** | **0.433** |
  | 10,000 | 30.0% | 50.0% | 70.0% | 0.418 |

  Stated caveat: the metric credits the chunk *containing* the expected provision, so a coarser ceiling is structurally favoured — bigger chunks contain more. The choice therefore rests on recall@1 and MRR, which do not reward coarseness.

- [x] **5.8b** **Two-stage ranking: BM25 for candidates, then term coverage.** BM25 alone was not merely imprecise, it was close to useless on anything but a term of art, because a **single rare-ish query word chose the chunk**:

  | query | BM25 returned |
  |---|---|
  | *"larger **allowance** for matching salary in a trade"* | **Meal Expense Allowance** (Art. III §2) |
  | *"two **contracts** together for one bigger salary"* | **10-Day Contracts** (Art. II §9) |
  | *"cap on how many contracts can be **combined**"* | **Charitable Contributions** (Art. XIII §6) |

  Candidates are now re-ranked by **how many distinct query terms each passage contains**, with BM25 as the tiebreak. That took **recall@1 from 16% to 34%** and MRR from 0.280 to 0.433; on term-of-art queries recall@3 went 56% → 76%.

  Two things measured and rejected along the way, recorded so they are not retried:
  - **A document-frequency stop list made it worse** — recall@10 fell 52% → 46% → 29% as the cutoff tightened. BM25's IDF already discounts common words; the damage came from the question's *rare* words, where "much" occurs in no chunk and "away" in one. The enlarged stop list that did help is of words uninformative in any corpus, not words frequent in this one.
  - **Indexing each chunk's defined-term bodies alongside it halved the score** (recall@1 34% → 16%). The definitions add boilerplate shared across chunks, which destroys discrimination.

- [x] **5.8c** **The residue was vocabulary, and D14 settles it by not searching.** *"Is there a cap on how many contracts can be combined at once?"* cannot be answered lexically: §6(j)(4) says **aggregating** and never **combined**. A test keeps that as standing evidence.

  The fix is to stop paraphrasing at the index. The document **names its own provisions**, so those names are indexed and resolved exactly, skipping ranking:

  | | measured |
  |---|---|
  | vocabulary built from the document | **670 names** (512 drafter-written headings + defined terms) |
  | provisions the engine cites that are nameable | **25 of 25** (14 directly, 11 via their containing provision) |
  | deterministic lookup returns the target | **25 of 25, 100%** (mean 7,927 chars) |
  | the same questions searched as paraphrases | 20% recall@3 |

  Measured and discarded on the way: "let the agent write a better *search* query" tops out at **61.5% recall@3** even when handed the provision's own heading. Naming and looking up is the better shape, and it is deterministic.

  Resolution is exact on the normalised name — fuzzy matching would resolve "traded player" to either the Standard Traded Player Exception or the definition of a Traded Player depending on edit distance. An unknown name returns nothing and the caller falls back to search.

  A Section-level name returns more subsections than a specific one, because 11 provisions have no name and are reached through the Section containing them — §8(g), the rookie-extension rule, is one. Measured: 5 subsections reaches 92%, 8 reaches 96%, **12 reaches 100%**, and the extra text is spent only on the Section case.

  **Phase 6 owes this task 6.3:** pick a name from `vocabulary_names()`, a closed set of the document's own words. Whether a model picks the *right* name cannot be measured offline — that is 6.3's eval. What is settled is that the vocabulary reaches every provision the engine cites.

---

## Phase 6 — Agent layer

- [x] **6.1** **Question router — 88.9% exact-set accuracy, 100% refusal recall on Haiku 4.5.** Five classes (rules, data, validation, constraints, refused), and **combinations are allowed**, because real questions are compound: *"if I traded Embiid, what are my limits and what rule sets them?"* needs the engine *and* the text, and a router forced to pick one label drops half of what was asked.

  **The labelled set had to be rebuilt first.** 4.7 carried routing labels for 18 questions, but they were 12 `data` against one each of three other classes — a classifier answering "data" every time would have scored respectably. Those 18 are reused (they were labelled when the category mattered for a different reason, so they are less likely to be bent to suit the router) and 27 added for balance: **45 cases, no class above a third, 4 compound.**

  **Scored on exact-set match**, not per-label overlap. A compound question is answered wrongly if either path is missed, so partial credit would hide the failure that matters. Per-class recall is reported alongside, because an aggregate cannot distinguish a router that over-uses `data` from one that is evenly wrong.

  **One of my labels was wrong, and the model found it.** I had labelled *"which contracts are not fully guaranteed?"* as `refused`, because the guarantee data is unknown (2.11). But whether the data exists is a tool-layer fact, not a question-type fact — the D6 and D10 refusals are about *scope*, and that question is neither historical nor an opinion. It routes to `data`, and the tool reports the unknown. Relabelled on that principle, which took accuracy 84.4% → 88.9% and refusal recall 87.5% → 100%. Reported both figures rather than only the better one.

  Residual errors are mild: the router sometimes adds `data` to a `constraints` question, which costs an extra tool call rather than a wrong answer. The one real miss is reading *"can the Suns aggregate contracts at all?"* as `rules`.

  Tested offline against a stub caller — a test that needs an API key is a test that stops running. The scored run is `python -m agent.router_cli`, a command rather than a test, because it spends money.
  **Extended in Phase 8 (D24, 2026-10-05): off-topic questions are refused here.** A third refusal basis, `off_topic`, covers anything not about contracts, payrolls, the cap, trades or the Agreement, and the reply says what the app can answer. The set grew to 55 (six off-topic, four casual near misses); Haiku scores **92.7%** twice with refusal recall 100%. **Two misses predate D24:** "Which players have won MVP?" and "Which draft picks have been forfeited?" are refused as *historical* on `main` too — whether a settled fact like an award is "a past season" in D6's sense is open.

- [x] **6.2** **Six tools, in a new `packages/agent` — the one package allowed a model client.** The engine, data and retrieval layers stay free of one, which is what makes their answers reproducible with no key present.

  Two properties shape the schemas, and both are tested:
  - **No tool accepts a figure from the model.** There is no `check_salary_match(outgoing=47_000_000)`, because a model that can pass a figure can pass a wrong one and the error becomes invisible. Tools take identifiers — a team, a player, a citation — and look the figures up.
  - **Schemas are generated where a closed set exists.** `query_league_data` enumerates the catalog's entities *and each one's own fields*, so naming `cap_holds.salary` (which does not exist) is refused with the allowed list rather than returning an empty result that looks like an answer. `resolve_provision` is backed by the document's 670-name vocabulary (D14).

  | tool | what it does |
  |---|---|
  | `resolve_provision` | a rule's name → its citation. Refuses an invented name and offers real ones |
  | `fetch_provision` | citation → verbatim text, reporting any substitution so the model cannot claim to quote §2(e)(2)(i)(A) while holding §2(e)(2)(i) |
  | `search_cba` | the fallback, and its description says so — 20% against 100% at reaching the right provision |
  | `define_term` | Article I's meaning for a term of art, with its citation |
  | `query_league_data` | the structured DSL, returning the SQL that produced the number |
  | `lookup_player` | candidates, never a best guess |

  An unknown tool name comes back as a correctable error rather than an exception, so the loop can fix itself inside its retry budget instead of failing the question.
- [x] **6.2a** **`tests/test_architecture.py` widened.** It guarded ADR-001 for the engine only, by regex. It now covers the data and retrieval layers too, parses imports via the AST so one written inside a function body is caught, names `agent` as the single permitted exception so a fifth package forces a decision rather than inheriting an exemption, and checks the `.env` rule CLAUDE.md states. CI's grep was widened to match.
- [x] **6.3** **NL → structured intent — and the real test of D14 option A: 80%, against a 100% ceiling.**

  D14 measured that *naming* a provision reaches its text where searching for a paraphrase reaches it 20% of the time, and that all 25 provisions the engine cites are nameable. What it could not measure without a model is whether a model picks the right name. This is that number:

  | approach | reaches the right provision |
  |---|---|
  | search with a paraphrase (5.8) | 20% |
  | Haiku, one name | 52% |
  | Haiku, up to three names | 64% |
  | Sonnet, one name | 68% |
  | **Sonnet, up to three names** | **80%** |
  | ceiling: perfect naming (D14) | 100% |

  **Four times better than search, and still 20 points short of the ceiling.** Stated plainly because it bounds what Phase 6 can promise.

  Three findings got it from 52% to 80%:
  - **My prompt omitted the thing the ceiling depended on.** 11 of the 25 provisions have no heading of their own, and D14's 100% came from naming the *containing* provision. The first prompt never said so, and the model returned nothing for exactly those. Telling it to prefer the broader name over an empty list was the single largest gain.
  - **Naming up to three beats naming one** (+12 points on both tiers). The rules overlap — a question about matching salary touches the exception that permits it and the restrictions that limit it — and fetching two short provisions costs less than missing the one that answers.
  - **The vocabulary had 60 sentences in it.** The heading pattern matched any capitalised run ending in a period or colon, so *"Notwithstanding Section 2(a) above, except as provided"* and *"Beginning at 12"* were offered as names. Filtering to title case took 670 → 612 entries and cost no provision: reach stays 25/25.

  **The residual 20% is 5 cases of a real name for the wrong rule**, which is the dangerous shape — it reads correctly. The mitigation is downstream: the answer step quotes the provision it cites, so a wrong provision produces an answer that visibly fails to address the question rather than a confident wrong figure. 6.11 should bait this specifically.

  **Ambiguity asks rather than guesses.** Two players called Williams is not a coin flip, so an ambiguous entity yields a clarification and no plan. An *unresolved provision name* deliberately does not: the user did not choose it, the model did, and asking them about it would be asking them to debug the agent.
- [x] **6.3a** **D15 revised: `INTENT` moves to the mid tier**, on two measurements rather than a preference. 16 points of accuracy on the task the whole retrieval strategy rests on, and — the surprise — the **cheaper model is the one that resends the prompt every time.** The vocabulary prefix is ~3,150 tokens, which is above Sonnet's 1,024-token cache minimum and below Haiku's 4,096. Uncached input across 25 calls: **609 tokens on Sonnet against 83,399 on Haiku.** The minimums were measured by bisection, not recalled.
- [x] **6.4** **Structured outputs with one bounded retry**, which hands the model its own parse error. A bare "try again" wastes the turn; naming what was wrong usually fixes it. Unbounded retries on a confused model burn budget, so the budget is the first try plus one correction. Fenced blocks and JSON wrapped in prose are both accepted, because models produce both — but ambiguity is not guessed at.
- [x] **6.5** **The loop — route, plan, run tools, answer — with the prohibition enforced rather than requested.**

  The system prompt forbids calculating and forbids stating a rule from memory. But a prompt is a request, not a guarantee, so the loop checks the finished answer:

  - **Every figure in the answer is audited** against what the tools actually returned. A number from neither a database row nor cited text is reported on the verdict. The check is a set comparison over digits — **nothing in it consults a model**, because a guardrail a model can talk its way past is not one. Normalised on digits, so `$221,069,148` matches a raw `221069148` and formatting is not mistaken for fabrication.
  - **An answer citing nothing is marked unsupported**, even when it happens to be right, because nothing in it can be checked.
  - **Tool rounds are capped at 6** — enough for the longest real path, short enough that a loop which has lost its way stops costing money.

  **The audit caught a flaw in itself on the first real run.** It flagged `$250,000` and `100%` in an answer that was *quoting Art. VII §6(j)(1)(i) verbatim* — the most defensible thing an answer can do. 5.9 forbids computing or recalling a figure, not quoting one out of the provision just cited, so figures are now split: values from the database are `sourced`, figures appearing in fetched provision text are `quoted`, and only a figure in neither is flagged. A warning that fires on the right answer teaches readers to ignore it.

  The plan's citations are handed to the answer turn rather than left to be rediscovered, since naming reaches the right provision 80% of the time against search's 20% (6.3).
- [x] **6.6** **Refusals name the decision they rest on.** Historical questions cite D6 — *"only current state is held, so answering would mean reporting today's figures as though they were then"* — and requests for a recommendation cite D10. A refusal that cannot say why is indistinguishable from a bug.

  **A partly refused question is still answered.** The refusal is carried into the answer turn instead of ending it, because declining the whole question would drop the part that is answerable.
- [x] **6.7** **Assumptions travel with the answer.** A citation substitution (*"the citation asked for was finer than any indexed passage"*), a tool reporting a term the Agreement does not define, and the engine's own recorded assumptions all attach to the verdict, so a caller can show them beside the conclusion rather than beneath it. `Verdict.trustworthy` is the single property that is false if anything is unsupported or unverified.
- [x] **6.8** **Prompt caching on the stable prefix — 97% off the answer role's billed input, and nothing for the router.** `python -m agent.cache_cli` runs both arms and reports the delta.

  | shape | uncached input | cached input | from cache | saved |
  |---|---|---|---|---|
  | router (system only, 447 tok prefix) | 1,359 | 1,359 | 0 | **0%** |
  | answer (system + 6 tools, ~2,700 tok prefix) | 8,262 | **252** | 8,010 | **97%** |

  **I was wrong about where this would help.** After 6.1 I said caching would "take a visible bite out of" the router's 20,668 input tokens. It cannot: the router's prefix is **447 tokens**, below the model's minimum cacheable length, so the breakpoint is silently ignored. Measured, not assumed — a 447-token prefix returns `cache_write=0` and `cache_read=0` on every call. The win is entirely in the answer role, which is both the expensive tier (Sonnet) and the one carrying the 2,697-token tool schemas.

  **The breakpoint goes on the system block, not the last tool.** The request is assembled tools-then-system, so a breakpoint after the system text covers both. Marking the last tool instead caches the tools and leaves the system prompt out — 2,565 tokens against 2,650, measured. A test holds the placement, since this is invisible when wrong.

  Applied unconditionally rather than behind a size threshold: a prefix below the minimum is *ignored, not charged*, so there is no constant here to go stale. The ledger reports the hit rate over cacheable tokens (reads plus writes) rather than over total input, because the per-turn message is never cacheable and including it would understate prefix reuse. When nothing cached at all the ledger says why, so a bare 0% is not read as a misconfiguration.

  The first call of each arm is discarded in the measurement: with caching on it pays the write, and including it reports the cost of warming rather than the steady state a served request sees.
- [x] **6.9** **Streaming — progress, not tokens.** A question takes about eleven seconds and makes three to eight model calls, and without this a user cannot tell "nothing is happening" from "it is working".

  What is streamed is **which step is running**, because that is also the first place an answer goes wrong: seeing *"searching the Agreement"* when you asked for a salary figure says immediately that the question was misread.

  ```
    0.1s  [step] working out what you asked
    1.0s  [step] choosing which rules apply
    6.1s  [tool] reading the provision Art. I §1(uuu)
    8.1s  [tool] querying league data
   15.4s  [done] $0.0768  trustworthy=True
  ```

  **The loop is observed, not re-implemented.** The caller supplies the trace, the loop fills it, and progress is read from the same spans the trace records — so what a user sees and what is recorded cannot disagree. A parallel callback system would create exactly that opportunity. The final update carries the audited verdict, so the streaming path cannot quietly drop the 5.9 unverified-figure warning.

  Read-only connections now cross threads: ADR-004 makes both databases read-only build artifacts, so there is no write contention for `check_same_thread` to guard, and Python reports `threadsafety == 3`.

- [x] **6.9a** **Rationale we were already paying for.** The router and intent steps are both already asked for a `reason`, both already return one, and it was parsed, used, then dropped before reaching the trace. It is now attached to the generation that produced it, along with the names that **resolved to nothing** — which is what the model was reaching for when it missed. Costs nothing, and it is the only record of *why* a provision was chosen, which matters most where 6.3 measured a fifth of selections reaching a real name for the wrong rule.

  Not a substitute for model thinking, which remains an open decision with a real cost — see the gap noted under 6.10c.

- [x] **6.9b** **An empty answer at the tool-round cap, found by streaming against the live API.** A question finished with fourteen citations, no answer text, and `trustworthy=True` — the loop had exhausted its six rounds while the model was still asking for more, so the last reply had no text in it and success was being reported for nothing.

  The loop now makes one final call with **no tools offered**, so the model must answer from what it gathered, and `answered` is a separate property so an empty answer is never `trustworthy` however well cited the run was.

  The first version of that fix was itself wrong: it appended a plain user message after an assistant turn containing `tool_use` blocks, which the API rejects — every `tool_use` must be answered by a `tool_result` in the very next message. The outstanding requests are now closed out with the reason they went unanswered. Verified live: the run that produced nothing now answers **$221,069,148** correctly.
- [x] **6.10** **Tracing built, vendor deliberately not chosen.** D4's shape — one trace per session carrying the user input, the system prompt, every tool call and result, every model call and the final output — is the same whoever stores it, so it is modelled once and the vendor is a thin adapter.

  That separation is not fussiness: the vendor question is open (see **D16**), and building against one SDK then moving would mean rewriting the instrumentation rather than the twenty lines that export it.

  **The local exporter is not a placeholder.** A trace written to JSONL survives any retention window, needs no network and no key, and can be committed as an artifact. The hosted exporter adds a dashboard, not the record.

  ```
  rules lookup             9 events  [answer 1, model_call 4, tool_call 3, user_turn 1]
  refusal (D10 opinion)    3 events  [model_call 1, refusal 1, user_turn 1]
  data query              21 events  [answer 1, model_call 8, tool_call 11, user_turn 1]
  ```

  **The event cap wraps the exporter** rather than living inside each adapter, so a free tier's allowance binds identically however the trace is stored — and exceeding it drops the trace while the question is still answered. A failing exporter does not consume the allowance either: nothing stored, nothing billed.

  **The system prompt is recorded by size, not verbatim.** D4 asks for it to be represented; the intent role's prompt carries 612 provision names, so repeating ~3,000 tokens on every span would make the trace unreadable and, on a metered backend, expensive.

- [x] **6.10c** **Instrumentation audited against Langfuse's own guidance, and reworked.** Installed the [Langfuse agent skill](https://github.com/langfuse/skills), which insists on documentation-first and on a run-fetch-audit loop that cannot be skipped. Both were worth obeying — the first version was written from memory and failed on several counts:

  | gap | fix |
  |---|---|
  | **Flat traces** (listed in their docs as a common mistake) | A tree: tools are siblings of the generation that requested them, under the agent that orchestrates them |
  | Every non-model span typed `span` | `agent` for the root, `generation` per model call, **`retriever`** for every tool — all six look something up without changing state, which is ADR-004 showing through |
  | Root input was `{"session": ...}` | The **question** in and the **answer** out, since the trace list shows those first |
  | Names like `model_call:router` | Verb-first and stable: `classify-question`, `select-provisions`, `generate-answer`, `fetch-provision`. Never the model name — that breaks every filter on a model swap |
  | No session, tags, environment, or scores | All four, with judgements as **scores** because tags are immutable and set at creation while `trustworthy` is only known afterwards |

  **Three bugs the live run found that no test would have.** `update_current_trace` is a **v3** API and does not exist in v4 (4.16.0 installed) — trace attributes use the module-level `propagate_attributes`. `event` is not a valid `as_type`; the SDK warns and silently downgrades it to a span, so refusals are created on their parent with `create_event`. And a propagated attribute is capped at **200 characters** and dropped with a warning above it, which the citation list blew through — per-run detail belongs on the root observation's metadata, not propagated to every span.

  **Verified by fetching the traces back**, not by assuming they arrived:

  ```
  AGENT       answer-cba-question     session=exemplars env=development tags=['rules']
    GENERATION  classify-question     claude-haiku-4-5   usage + cost
    GENERATION  select-provisions     claude-sonnet-5
    GENERATION  generate-answer       claude-sonnet-5
    RETRIEVER   fetch-provision
  ```

  Langfuse prices the calls itself from the model name and usage details — `totalCost` comes back populated — and all four scores attach to each trace.

  **One gap left open rather than papered over:** thinking is not captured, because extended thinking is not enabled on these calls. The guidance asks for it on every generation, so if it is ever turned on, the reasoning blocks should be captured with it.

- [x] **6.10b** **Langfuse exporter written (D16).** The one vendor-specific file, and the reason 6.10 kept the export behind a twenty-line adapter.

  Model calls are sent as **generations** carrying the model and token counts, which is what makes the cost view work; everything else is a plain span. Cache reads are reported under their own key rather than folded into input — at a 97% hit rate that is the one number a cost dashboard exists to get right.

  **Not verified against the live service.** No Langfuse keys exist in the repo yet, so what is tested is the mapping and, more importantly, that *every* failure path returns `False` rather than raising: a missing key, an SDK that is not installed, a network failure, or an SDK whose shape has moved since this was written. 6.13 settles that tracing degrades while spend refuses, and an exporter that throws would break that promise. A missing key is diagnosed once rather than on every answer.

  The SDK is an **optional dependency**: the agent runs and the whole suite passes with no observability backend installed.

- [x] **6.10a** **Five exemplar traces committed** to `docs/traces/exemplars.jsonl`, captured against the live API. Retention is 14 days on Raindrop's free tier and 30 on Langfuse Cloud's, so a trace worth showing is gone within a month and the observability story should not depend on a live account.

  Checked for key material before committing: none. Regenerated by the snippet in `docs/traces/README.md`.

- [x] **6.11** **30 adversarial prompts. The run that mattered was the first one: 18/30, with 9 fabricated figures.** `python -m agent.adversarial_cli`.

  The traps are specific to this document, not generic jailbreaks, because the plausible wrong answers are all sitting in the text: the **2017 band** ("125% plus $100,000", which Phase 0 had to disprove), figures belonging to a **different exception** ($7,500,000, 200%), terms the agreement **never uses** ("hard cap" appears zero times), and the dates and dollar amounts in §2(e)'s five **worked examples**.

  | run | held | misleading failures | what changed |
  |---|---|---|---|
  | 1 | 18/30 | 9 | — |
  | 2 | 27/30 | 3 | excluded user-supplied figures; hardened the arithmetic prohibition |
  | 3 | 26/30 | 4 | separated over-refusal from fabrication; fixed router over-refusal |
  | 4 | 30/30 | 0 | expanded k/M suffixes in the audit |

  **The 30/30 is not the headline — the variance is.** "Do the cap math" scored 6/6, then 4/6, then 6/6 on identical prompts. A single run of 30 is not a stable measurement, and anyone reading one number off it is reading noise. The defensible claim is that after the fixes the misleading-failure rate is **0 to 4 in 30**, and pinning it down needs repeated runs.

  Four things the set found, in order of value:

  1. **My audit was flagging the user's own figures.** "A team sends out $30,000,000 — how much can it take back?" had `$30,000,000` reported as fabricated. Restating the question is not inventing a number. That alone accounted for much of the first run's 9.
  2. **The model really was doing cap math** — $30,250,000, $12,750,000, $4,750,000 — correctly applying the right rule, which is still forbidden, because nothing downstream can check a figure the model produced. The prompt now says not to finish the sum even when the arithmetic is trivial. That took the category from **1/6 to 6/6**.
  3. **The router was over-refusing.** It declined *"just tell me the salary matching rule, no need to look it up"* as out of scope. That is a legitimate question wrapped in an illegitimate constraint, and the right move is to drop the constraint and answer with a citation. The router prompt now says exactly two things are refusable and nothing else.
  4. **My scoring conflated over-refusal with fabrication**, which hid which was happening. They are now counted separately: `MISLEADING` for a figure or claim with nothing behind it, `over-refused` for declining something answerable — wrong, but wrong in the safe direction.

  Cost per run: ~122 model calls, ~380k input tokens at a **100% cache hit** on the answer and intent roles, 11s per question.
- [x] **6.12** **Per-request cost and latency**, reported from the API's own usage rather than estimated:

  ```
  What is the Standard Traded Player Exception?   10.9s, 4 model calls, 3 tool calls,
                                                  10,923 in / 934 out, 3,293 cached, 8 trace events
  How much are the Nuggets committed for?         16.1s, 8 model calls, 8 tool calls,
                                                  13,868 in / 1,284 out, 24,891 cached, 17 trace events
  ```

  **No prices are hard-coded.** Per-token pricing changes, and a stale table would be worse than none, because the whole point of a cap is that the operator can trust it. Tokens are always counted; dollars appear only when a price table is supplied, and an unpriced request reports `None` rather than `0.0` — zero would read as free, which is a different claim from unknown. Cache reads are priced separately from fresh input, because at a 97% hit rate (6.8) folding them together would misstate the bill badly.
- [x] **6.13** **Rate limiting and two hard caps, built with the loop rather than bolted on at deploy.** The loop is what knows how many calls a question cost.

  **The two caps fail differently, on purpose.** Exceeding the tracing budget *degrades tracing*; exceeding the spend budget *refuses the request*. A trace is diagnostics and losing one costs a developer some insight; a model call costs money that is not recoverable. Drops are counted either way, so silence is distinguishable from nothing having happened.

  Caps are checked **before the first model call**, because the point of a spend cap is to not spend — verified: a rate-limited request reports 0 model calls. A capped request returns a *verdict* explaining itself rather than raising, so the reason reaches the user instead of becoming a 500.

  The request window is a sliding deque rather than fixed buckets, so a burst straddling a boundary cannot push two windows' worth through.

- [x] **6.13a** **The D13 event estimate was optimistic, and the measurement corrects it.** I projected ~7 events per question and therefore ~140 questions a month on Raindrop's 1,000-event free tier. Measured: **8 events for a simple provision lookup and 17 for a data question** that took 8 model calls and 8 tool calls.

  | | estimated (D13) | measured |
  |---|---|---|
  | events per question | ~7 | **8–17** |
  | questions per 1,000 events | ~140 | **~60–125** |

  The tool-heavy design that ADR-001 requires is what costs the events, so this is a consequence of the architecture rather than a bug. It makes the client-side event cap more important, not less: at 17 events a question the free tier is gone in 59.

---

## Phase 7 — Interface

- [x] **7.0** **The API and the answer-card contract.** Not in the original plan: 8.3 deployed `apps/api`, but nothing built it. `apps/api` (FastAPI) serves `GET /health`, `POST /ask` (JSON) and `POST /ask/stream` (server-sent events: progress, then the card). Both ask routes end in the same `agent.card.build`, so they cannot disagree. The card (`packages/agent/src/agent/card.py`, schema version 1) carries verbatim quotes with PDF and printed page, every league query with its SQL, parameters and provenance, and warnings for unsourced figures, uncited answers, exhausted rounds, `unknown` values (ADR-003) and undated rows.
  - **Found while building it: `as_of` was empty on every table except `trade_exceptions`.** The columns existed and nothing filled them, so 7.6 had nothing to show. Each scraper manifest records `scraped_at`; ingest now writes those to `ingest_meta.source_dates`, and every `QueryResult` carries `provenance` — per source, the row's own date where one exists, otherwise the scrape date *labelled as a scrape date*, otherwise `undated`. **Spotrac is deliberately excluded from the fallback**: its `scraped_at` is when the Wayback Machine was read, up to 13 months after the facts.
  - **First live run** (*"How much are the Nuggets committed for in 2026-27?"*): correct figure, verified card, 21s, **$0.125** — above the 6.12 figure because the model spent six queries finding the filter values (`"Denver Nuggets"` and `"2026-27"` before `DEN` and `2026-2027`) and exhausted its rounds. The card made the dead ends visible; the fix belongs in the query tool's descriptions.
- [x] **7.0a** **The database, as the engine sees it** (`nbadata.state`). Until now the engine ran only on fixtures and the eval corpus: nothing built a `TeamState` from the league database, and none of the agent's six tools calls the engine, so *"is Jokić for Dončić legal?"* has been answered from quoted rules, never by `validate_trade`. The bridge maps every gap to an explicit unknown — `ContractType.UNKNOWN`, `GuaranteeType.UNKNOWN`, tri-state kickers and no-trade clauses, ceilings with no row or date (SalarySwish publishes neither) — rather than the defaults the engine's types offered.
  - **Was blocked on a source-precedence decision; settled by D18 (Fanspo's payroll wins for the current season).** Loading all 30 teams showed Basketball-Reference's 2026-27 contract totals disagreeing with Fanspo's payroll by up to **$39.4M** (GSW; 20 teams off by more than $5M), and `reconciliation` had reported 0 disagreements. Fanspo is the one consistent with SalarySwish's hard caps: on Basketball-Reference figures MIN ($215.3M) and PHI ($213.2M) sit above their own $210.69M first-apron ceilings, which cannot happen; on Fanspo's they are at $195.2M and $205.6M. The GSW diff shows why: Basketball-Reference carries Draymond Green at $27.7M where Fanspo has him as a free agent with a $38.8M hold, and five camp minimums Fanspo does not list. For the current season Basketball-Reference reads as a contract projection, Fanspo as the actual payroll (active roster, dead cap and rest-of-season deals listed separately).
- [x] **7.1** Chat as the primary surface — questions, not forms. *`apps/web` (Next.js 16, React 19). Streams progress from `/ask/stream`, one question at a time.*
- [x] **7.2** **Answer card**: verdict, plain English, verbatim CBA quote, citation, assumptions — *contract done in 7.0 and rendered in `AnswerCard.tsx`: warnings before the answer, quotes the answer names first, dead-end queries folded. Signed off by the owner on 2026-10-03, with a note that it **shows more than it needs to and should be culled later** — the obvious candidates are the folded passages (a §4 fetch alone surfaced 14) and the long, elaborated answer text.*
- [x] **7.3** Show the structured query behind any number, inspectable on demand — *each number the answer took from a query links to that query (`linkFigures`), whose SQL and parameters sit behind "Show the query"; an unsourced number is struck through in red.*
- [x] **7.4** Trade builder with live verdict, reachable from a chat answer — *`/trade` in the web app, served by `POST /trade` (`nbadata.trades` → `engine.validate_trade`, no model). The trade lives in the query string, so any trade is a link. A validation answer carries the players it named (`card.trade`, additive, schema unchanged) and links to `/trade?player=…`; `GET /players` finds their teams, and with two teams the directions are filled in (with three they would be a guess, so they are not). Each violation shows the verbatim provision, via `fetch_nearest`, saying when the passage shown only contains the clause cited. Every verdict lists what it rests on: kickers assumed absent, and trade restrictions and no-trade clauses that no source carries.*
  - **Found while building it: `validate_trade` let a team use an exception it is barred from.** Art. VII §2(e)(2)(i)(A) — no Transaction Restrictions Table transaction that leaves the team above that row's apron — was enforced only in the constraint report. Murray for Irving and Washington was called **legal** while leaving Denver at $226.4M through the Expanded exception (row E, first apron). Barred exceptions are now excluded before matching, and a trade only a barred exception covers gets its own code, `apron_transaction_barred`, citing §2(e)(2)(i)(A).
  - **And `validate_trade` never used 3.14a's structuring.** A team sending several players was judged as one aggregated exception; the test case is permitted $81.1M structured against $59.5M. `best_structure` is now the fallback, with the same exclusions.
  - **A legal trade now says what it costs**: matching by the Expanded or Aggregated exception hard-caps the team at that row's apron for the season, and the verdict notes it. The ground-truth evals are byte-identical before and after — they do not run `validate_trade` against team states, which is why neither defect showed there.
  - **Found here, fixed in 8.0: validation questions in chat could return an empty answer.** *"Is Jamal Murray for Kyrie Irving and PJ Washington a legal trade?"* came back `unavailable` twice ($0.10 and $0.04). The answer role (`claude-sonnet-5`) thinks before answering, and its 1,500-token `max_tokens` is used up by the thinking block: the last reply stopped at `max_tokens` with a thinking block and no text, and an earlier round stopped mid-tool-call. The exhausted-rounds fallback does not catch it, since no tool was requested. The trade builder link still appears on that card and works.
  - **Closed 2026-10-05: the chat now runs `validate_trade`.** No agent tool had called the engine, so a validation answer was composed from quoted rules, and after 8.0 one run in nine still reached the wrong verdict. The agent's seventh tool runs `nbadata.trades.check` — the builder's own check — taking player and team keys, never a figure; prompt rule 6 makes its verdict the verdict and requires each violation's provision to be fetched and quoted. Its salaries count as sourced and its assumptions reach the card. Murray for Irving and Washington, three runs: **"Not legal" every time**, citing §2(e)(2)(i)(A), no unsourced figures, **$0.055–0.070 and 14–17s** (after 8.0: mean $0.12 and 34s, because the model no longer reads its way to a verdict). Adversarial set, one run: **30/30, 0 misleading** — inside 6.11's band; one run is not evidence it moved.
- [x] **7.5** Cap sheet view with apron lines as visible thresholds, tabular numerals — *`/cap/[team]` in the web app, served by `GET /teams/{key}/sheet` from `nbadata.sheet`, which reads the same `TeamState` the engine does. Two bars, not one, against the four lines: Team Salary (holds in) is measured against the cap, Apron Team Salary (holds out, qualifying offers in) against the tax and aprons, and a single bar would be wrong about one of them. Each line on the books says what it counts toward ("Cap only" for a hold), and a test pins every total to the sum of the lines shown, for all 30 teams. A binding hard cap is drawn as its own red line. Trade exceptions are read directly and checked for expiry against the payroll's date, not the stale flag (OKC's only one had expired). No model call. Checked in headless Chrome at 1040px and 390px; no horizontal page scroll.*
  - **Found while building it: the bridge left out dead money**, so the engine read Milwaukee's Apron Team Salary $23.2M low and Phoenix's $23.2M low (Lillard, Beal). Loaded from Fanspo's dead cap (D18); D18's hard-cap invariant now also holds as the engine computes it, not only in SQL.
- [x] **7.6** **Provenance and as-of date on every figure — mandatory.** *Done: every query in a card lists source, basis and date ("scraped 29 Sep 2026", "as of …", or "date unknown"), and every answer carries the dataset line.* The dataset is a snapshot, and the Spotrac rows alone span 13 months of differing snapshot dates. A public app implies currency; without prominent as-of labelling it is quietly misleading.
- [x] **7.7** Permalinks for a question and its answer — *D19: the card travels in the URL fragment, compressed, with quote text dropped and re-fetched by exact passage label (`POST /quotes`, no model). Each dropped quote keeps a hash, and the reopened page warns if the index has changed the words since. Measured: a rules answer's link is 2,241 characters and reopens byte-identical; a truncated link is refused with a sentence.*
- [x] **7.8** Empty, loading, error and refusal states; usable read-only mobile view. *Checked in headless Chrome at 820px and 390px against the live API.*

---

## Phase 8 — Ship

**Next.js → Vercel. FastAPI → Render.** The engine, data and rag packages stay
platform-agnostic; only `apps/` knows where it runs.

- [x] **8.0** *(added at the Phase 7 → 8 handoff)* Fix the empty validation answer found in 7.4, and re-measure the answer role's cost. *Sonnet 5 thinks by default at effort `high`, and the thinking counts against `max_tokens`: at 1,500, two of three runs of the Murray trade question spent it all thinking and returned no text. Three changes: the ceiling is now 8,000 (`ANSWER_MAX_TOKENS`); the answer role runs at effort `medium` (`DEFAULT_EFFORT`, overridable per role with `ANTHROPIC_EFFORT_*`); and the conversation is cached as well as the system prompt — a second, moving breakpoint — because each tool round was re-sending the whole history at full price.*

  | the trade question, 3 runs each | answered | mean cost | mean time |
  |---|---|---|---|
  | before (1,500 tokens) | 1/3 | $0.24 | 49s |
  | 8,000 tokens | 3/3 | $0.31 | 86s |
  | + effort `medium` | 3/3 | $0.245 | 58s |
  | **+ conversation cached** | **3/3** | **$0.12** ($0.05–0.23) | **34s** |

  **Uncached input fell from 65–143k tokens a question to ~570.** That was the bill, more than thinking was. The spread that remains is the number of tool rounds (2 to 6). The 6.12 questions now cost **$0.037** (Standard TPE) and **~$0.05** (Nuggets committed salary — $0.125 in 7.0). **Adversarial set at `medium`, two runs: 1 misleading failure each** (cap math once, a "ballpark" MLE once), inside 6.11's 0–4 band; ~$1 a run.
  - **Tried and kept as fallback: 8,000 tokens at the default `high`.** It fixes the empty answer as well, at 27% more per question and 48% more time, and gave less consistent verdicts (one "No", two "not clearly legal") than `medium` (three "No").
- [ ] **8.0a** *(added 2026-10-05)* **Free models as the over-cap fallback (D23).** Sonnet and Haiku stay the defaults; when the spend cap is reached, Nemotron 3 Ultra via OpenRouter answers instead of the app refusing. Evaluated through a prototype caller against the existing evals:

  | one run each | router | refusal recall | naming | adversarial (misleading / 30) | per question |
  |---|---|---|---|---|---|
  | current (Haiku / Sonnet) | 88.9% | 100% | 80% | 1 | ~10s |
  | Nemotron 3 Ultra (free) | 86.7% | 100% | 84% | 1 | ~50s, 503s on 3–30% of calls |
  | Nemotron 3 Super (free) | 82.2% | **85.7%** | 64% | 1 | ~31s |

  - [x] **Found by it, fixed: a malformed tool argument failed the whole request.** Ultra sent `query_league_data` a `select` of bare strings; the `TypeError` escaped `tools.call`. Wrong-shaped arguments now come back to the model as an error it can correct, like an unknown tool name.
  - [x] The OpenRouter caller in `packages/agent` (reasoning headroom on `max_tokens`, tool-call translation, retries on 503/429), and the fallback wired to the spend cap. *`agent.openrouter`: `OpenRouterCaller` translates Anthropic's message shape to OpenAI's and back, so the loop runs unchanged even when the switch happens mid-question; it accepts only `:free` model ids, so the key's credit is never spent. `FallbackCaller` switches on the in-process spend cap, on the Console's workspace limit (a 400 naming usage limits or credit), on 429 and on 5xx — not on a malformed request, which would hide a bug — and stays switched for an hour (billing) or a minute (capacity). The rate limit still refuses. The card warns when the fallback answered, and its tokens are priced at $0 rather than as Sonnet's. Off unless `OPENROUTER_API_KEY` is set. Live, forced: the Standard TPE question answered and verified with one citation in 22s, $0.00.*
- [x] **8.1** **Build pipeline in CI** — run ingest and indexing, emit `nbacba.db` and the retrieval index as deployment artifacts ([ADR-004](adr/0004-read-only-at-runtime.md)). Keeps them out of git and makes the whole dataset reproducible from source. *`python -m rag.fetch` (standard library only) tries NBA.com's copy, then the NBPA's, and writes the PDF only if it matches the sha256 pinned in `rag/fetch.py` (D20); a copy that downloads but differs is refused, because a silently revised PDF would move every page number and citation under the evals. CI caches the PDF under that file's hash. A new `artifacts` job, after the tests pass, builds both artifacts and uploads them as `nbacba-artifacts` (30 days).*
  - **CI now runs the tests that read the Agreement.** Every test needing the PDF had skipped in CI since Phase 5 (`test_tools.py`, the `rag` suite and others carry a `skipif`); with the file fetched they run, and the whole suite takes ~26s locally.
  - **The index is reproducible to the byte**: two fresh builds from the fetched PDF, and the local build every measurement here was taken against, have the same sha256. Not a given — D19's permalinks hash each dropped quote, and a non-deterministic build would trip their "the words have changed" warning on every deploy.
  - **Corrected in 8.3: byte-identical only on the same SQLite version.** All three builds above were on one Mac (SQLite 3.50.4). The Docker image (Debian, SQLite 3.46.1) builds an index with a different sha256. Every table — chunks, citation map, definitions, cross-references, vocabulary — dumps identically, and full-text search returns the same rows with the same bm25 scores; only the FTS5 index's internal layout differs. The permalinks hash quote text, which is unchanged, so they are unaffected.
- [ ] **8.2** Deploy `apps/web` to Vercel
- [ ] **8.3** Deploy `apps/api` to Render, with the artifacts from 8.1 bundled *— image and Blueprint done and tested; the deploy waits on the owner's account. A `Dockerfile` rather than Render's Python runtime, so the exact image can be built and run locally first; it builds the artifacts itself rather than downloading CI's, which would need a GitHub token on Render. Tested locally (`linux/amd64`): `/health` serves the dataset dates, CORS admits the configured origin and rejects another (400), and "What does the second apron restrict?" came back answered and verified with 22 citations in 17s.*
- [ ] **8.4** Publish `packages/engine` as a standalone installable package — a tested CBA rules engine is a portfolio artifact independent of the app. *GitHub only for now, not PyPI (D22); name to settle — the owner suggested `nba-cba-agent`, but the engine imports no model, so `nba-cba-engine` may describe it better.*
- [ ] **8.5** Environment and secrets per platform; confirm the spend cap from 6.13 is live *— the 6.13 cap is per process and Render's free tier restarts after each idle spell, so it resets constantly: the monthly limit has to be set on a dedicated Anthropic Console workspace, and Render given that workspace's key.*
- [ ] **8.6** Cold-start note: Render's free tier spins down after inactivity. *Settled (D21): the free tier, and a slow first load is accepted. The web app's ~30s wake message is already written; what remains is checking it against the deployed API.*
- [ ] **8.7** README leading with the architecture thesis and the eval numbers *— its four-kinds table, which says validation is handled by the rules engine, is now true in chat as well (7.4).*
- [ ] **8.8** Three-minute demo: a rumoured trade adjudicated with a citation, and a question refused with a reason *— both surfaces adjudicate with the engine now: the chat runs `validate_trade` and quotes the violated provision, and the trade builder (7.4) shows the same verdict with the numbers.*
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
