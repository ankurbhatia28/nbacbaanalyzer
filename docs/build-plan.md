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
- [ ] **1.15** **Apron *status* and apron *ceiling* are separate fields.** Status is where a team's Apron Team Salary sits. Ceiling is what a prior transaction forbids it from exceeding. Houston is far *below* the second apron yet may not cross it; OKC is far *above* it and may go higher. A single "apron" field conflates opposite situations.
- [ ] **1.16** **`HardCapCeiling` is a set, not a scalar.** One entry per triggering transaction — `(trigger_row, apron_level, effective_date, source_transaction)` — with the operative ceiling computed as the **minimum**. Confirmed against real data: Milwaukee holds a first-apron ceiling (Jul 8 expanded-TPE acquisition) *and* a second-apron ceiling (Jun 24 cash payment); trackers show 1st because the lower one binds.

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
- [x] **2.11** **`guarantee_kind` now reads `unknown`, not `full`.** The schema defaulted it to `'full'` and the loader wrote `'full'` positionally, so all 1,136 contract-years claimed to be fully guaranteed — while the scraped CSV has no guarantee column at all. Basketball-Reference marks guarantee status with cell styling the scraper never read, so the value was asserted, not observed, in breach of [ADR-003](adr/0003-unknown-is-not-zero.md). The catalog advertised "full, partial or none" on a column that could only ever say one of them. Found by writing the 4.7 question "which contracts are not fully guaranteed?", which returned an empty list — readable as "none", which was false. Closing it properly needs a source that publishes guarantee dates and amounts.

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
- [x] **3.6** First apron restrictions — **derived, not transcribed.** The CBA has no such list; the restrictions fall out of Art. VII §2(e)(2)(i)(A) — a team may not use a Transaction Restrictions Table row if it would exceed that row's level immediately after. Rows A–F close above the first apron.
- [ ] **3.7** Second apron restrictions — aggregation, prior-year TPEs, cash, taxpayer MLE, frozen pick
- [ ] **3.8** Hard cap ceilings. The CBA never says "hard cap" — the mechanism is Art. VII §2(e)(2)(i)(B), driven by the **Transaction Restrictions Table** (§2(e)(4), pp. 214–215), **rows A–K**. Encode all eleven: A–G set the **first** apron (bi-annual exception, non-taxpayer MLE, sign-and-trade acquisition, waived-player signing above the MLE, expanded TPE, post-season standard TPE, transition TPE); H–K set the **second** (aggregated TPE, **paying cash in a trade**, TPE from a signed-and-traded contract, taxpayer MLE). §2(e)(2)(ii) makes rows E–J executed after the Regular Season bind the *following* Salary Cap Year.
- [x] **3.9** Stepien rule — **implemented from the NBA Constitution and By-Laws §7.03** (p. 85), where it is unnamed. No provision restricts assigning draft picks between teams; the rule lives in the NBA Constitution and By-Laws, which p. 322 explicitly holds separate ("nothing contained in this Agreement shall be deemed to be an agreement of the Players Association to any provision of the NBA Constitution and By-Laws"). Two prohibitions: no selling first-round pick rights for cash, and no trade whose result *may be* to leave a Member without first-round picks in any two consecutive future Drafts. Cited as a By-Law, not a CBA provision, since the documents have different force.
- [x] **3.10** ~~Base year compensation~~ — **eliminated.** "Base Year" appears **zero** times in 676 pages. The term is definitional, so its absence is conclusive rather than suggestive. The rule does not exist under the 2023 CBA.
- [x] **3.11** Poison pill — **located and implemented.** The nickname covers two provisions sharing one mechanism: Art. VII **§8(g)** (Rookie Extension Trade Rule, pp. 288–289) and Art. XI **§5(d)** (Gilbert Arenas, pp. 346–347). Both deem a salary to equal the average of a contract's remaining years, for one party's Room only. I had searched §7 (Extensions); the trade-valuation rule lives in §8 (Trade Rules).
- [ ] **3.12** Trade kickers — honouring `Unknown` rather than assuming zero. **Source found:** Hoops Rumors publishes an annual list with percentages ([2026/27](https://www.hoopsrumors.com/2026/08/nba-players-with-trade-kickers-in-2026-27.html)). **Settled:** the **sending** team pays the player (Art. XXIV §2(a), p. 438), but the bonus lands in the **acquiring** team's Team Salary and counts as incoming trade salary for matching — so the engine's existing treatment was right. Teams may alter the payment arrangement between themselves, governed by cash-in-trade (Art. VII §8(a)), which does not move the cap hit. **A player may also reduce or waive the bonus** (§2(a)(iii)(B)(3), p. 439), so a deal failing *only* on a kicker is conditional, not illegal — the constraint report now says so instead of marking it blocking. Keyword search did not surface a single clause stating the acquiring-team attribution; it is recorded on the user's domain knowledge, consistent with §2(a) and p. 295.
- [x] **3.13** Trade date calendar — Art. VII §8(c)–(d). Four rules with separate clocks: no trade after the deadline in a possible final Season; 30 days for rookies and two-ways; later of 3 months or **December 15** for free agent signings; later of 3 months or **January 15** for a prior-team re-signing above **120%**. The last bars the *trade*, not merely aggregation — distinct from the two-month bar in §6(j)(4)(i).
- [x] **3.14a** **Structuring across several exceptions.** Art. VII §6(j)(1)(i) lets one exception replace "one (1) Traded Player", and §6(m) carves §6(j) out of its bar on combining Exceptions — so a team sending several players may use several. Modelling a trade as a single exception understated capacity: four contracts totalling $47.4M permit **$81.1M structured vs $59.5M** as one exception. `best_structure()` enumerates the partitions. Found by the eval harness, not by reading — 14 of 20 undetermined legs acquired two or more players.
- [ ] **3.14** Simultaneous vs non-simultaneous trades and TPE creation
- [ ] **3.15** Multi-team trades — validate each team's send and receive independently
- [ ] **3.16** Roster counts and pick tradeability
- [ ] **3.17** **Violation code → CBA citation table.** The join between engine and retrieval; the reason citations are right
- [ ] **3.18** `validate_trade(legs, as_of) -> Verdict` with violations **and assumptions**
- [x] **3.19** **`team_trade_constraints(team, player) -> Constraints`** — enumerate everything limiting a team, without a proposed deal. Answers the Embiid question. **Built.** Hard-cap ceilings (binding and superseded), player-level restrictions, trade kickers, and now:
  - **the Transaction Restrictions Table rows the team may not engage in** — the substance of the answer, since being over an apron does not stop a team trading, it stops it trading in particular *ways*
  - **first-round pick tradeability, asked one pick at a time.** A team can be free to move one year's first and barred from moving another's, so a single yes/no over the inventory would be wrong. On the real Clippers position (firsts in 2027/29/31/33, bare in 2028/30/32) every held first is untradeable while the position itself is legal
  - trade-date windows, with the flags we lack recorded as assumptions — a bar not evaluated reads as "tradeable"
  - the roster minimum and maximum, which shape how a deal may be built
  - **take-back capacity in dollars** via `best_structure` — a list of prohibitions is not the whole answer
  - no-trade clauses, tri-state: unknown is surfaced, absent stays quiet

  Two fixes fell out of it: `RestrictionRow.describe()` (the rows had no human-readable phrasing, so prohibitions would have rendered empty), and a **miscitation** — `TransactionPermission` cited §2(e)(2)(i)(**B**), the ceiling that attaches *after* a permitted transaction, for a rule that implements (i)(**A**), the prohibition itself. Added `TRANSACTION_PROHIBITION` with the verbatim text from p. 211.

  Still absent rather than approximated: Art. VII §2(f) (the Second Apron pick freeze, **not implemented** despite a citation existing for it) and the seven-Drafts-ahead horizon.
- [ ] **3.20** Every verdict carries the assumptions it rests on (ADR-003)
- [x] **3.21** Property-based tests — invariants across the input space: permission is monotonic in salary, expanded is never worse than standard, a returned allowance always fits, more ceilings only tighten, more lost picks never make Stepien pass, an unknown always records exactly one assumption.
- [ ] **3.22** Golden tests from the CBA's own worked examples

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
- [ ] **6.10** **Tracing via Raindrop — one trace per user session.** Each trace carries the user input, system prompt, every tool call and result, retrieved context, every intermediate model call, and the final user-facing output. **Cloud, Hobby tier (D13).** Raindrop bills per *event*, and an event is one logged interaction — a user turn, an agent response, or a tool call. This architecture is deliberately tool-heavy, so one question costs roughly:

  | | events |
  |---|---|
  | user turn | 1 |
  | router + intent model calls | ~2 |
  | tool calls (DSL query, retrieval, engine) | ~3 |
  | final response | 1 |
  | **per single-question session** | **~7** |

  1,000 events/month is therefore **~140 single-question sessions**, fewer once conversations run multi-turn. Two consequences for 6.13: the event budget needs enforcing client-side rather than trusting the vendor to stop at the cap (unconfirmed, and not worth depending on either way), and exceeding it must degrade tracing, never fail the request.

- [ ] **6.10a** **Retention is 14 days on the free tier**, so a trace worth showing is gone within a fortnight. Persist a handful of exemplar traces as repo artifacts so the observability story is always demonstrable, independent of the live account.
- [ ] **6.11** Adversarial eval — ~30 prompts engineered to bait the model into doing cap math or asserting a rule unaided. Assert it always calls the tool.
- [ ] **6.12** Cost and latency tracking per request
- [ ] **6.13** **Rate limiting and two hard caps — model spend and Raindrop events**, built with the agent loop rather than bolted on at deploy. A public URL in front of a model key is not deployable without them, and the 1,000-event tracing budget (6.10) is exhausted by roughly 140 questions.

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
