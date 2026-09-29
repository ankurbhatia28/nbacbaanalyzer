# Constants to verify

> **Verified 2026-09-29.** Every section below was checked against
> `data/cba/nba-cba-2023.pdf` by a second reader. Two corrections came out of it,
> both recorded in place: Transaction Restrictions row G is unreachable for any
> season we model (§2(e)(5)), and the Maximum Annual Salary section had the wrong
> tier boundary, a missing tier, and a missing 105% alternative.
>
> This file stays as the record of what was checked and when. **Adding a constant
> means adding a row here and re-verifying it** — an unverified value is one that
> propagates silently into every verdict the engine gives.

Values transcribed from the CBA into `packages/engine`. I can transcribe
accurately but cannot independently confirm that I did; a second reader is the
only real control. Page numbers are the PDF's own.

## 1. Salary matching — Article VII §6(j)(1), pp. 264–266

**The highest-priority block.** The commonly cited "125% + $100,000" is the
**2017** CBA. If the values below are wrong, every matching verdict is wrong.

| ✅ | Constant | Value encoded | Citation |
|---|---|---|---|
| ✅ | Flat allowance | **$250,000** (not $100,000) | §6(j)(1) |
| ✅ | Standard TPE | **100%** of pre-trade salary + allowance | §6(j)(1)(i), p. 264 |
| ✅ | Aggregated Standard | **100%** of aggregated salaries + allowance | §6(j)(1)(ii), p. 264 |
| ✅ | Transition TPE | **110%** + allowance, **2023-24 only** | §6(j)(1)(iii), p. 265 |
| ✅ | Expanded TPE | greater of **(y)** lesser of [200% + allowance] and [100% + $7.5m × cap_now ÷ cap_2023-24], or **(z)** 125% + allowance | §6(j)(1)(iv), p. 265 |
| ✅ | Room absorption | cap room + allowance; **may not** be combined with (i)–(iv) | §6(j)(1)(v), p. 265 |
| ✅ | Allowance removal | allowance → **$0** if post-assignment Apron Team Salary would exceed the First Apron Level | §6(j)(3), p. 266 |
| ✅ | Expanded base year | $7.5m scales against the **2023-24** cap ($136,021,000) | §6(j)(1)(iv)(y)(B) |

## 2. Transaction Restrictions Table — Article VII §2(e)(4), pp. 214–215

Eleven rows, not the handful usually cited. Rows A–G set a **first** apron
ceiling; H–K a **second**.

| ✅ | Row | Transaction | Apron |
|---|---|---|---|
| ✅ | A | Bi-annual Exception | First |
| ✅ | B | Non-Taxpayer MLE | First |
| ✅ | C | Acquiring a player on a §8(e)(1) contract (sign-and-trade) | First |
| ✅ | D | In-season signing of a waived player paid above the Non-Taxpayer MLE | First |
| ✅ | E | Expanded Traded Player Exception | First |
| ✅ | F | Standard TPE used after the Regular Season in which it arose | First |
| ✅ | G | Transition Traded Player Exception | First *(see note)* |
| ✅ | H | Aggregated Standard TPE | **Second** |
| ✅ | I | **Paying cash** to another team in a trade | **Second** |
| ✅ | J | TPE arising from a signed-and-traded contract | **Second** |
| ✅ | K | Taxpayer MLE | **Second** |

**Note on row G.** The apron level is transcribed correctly, but the row is
unreachable for any season we model. The Transition exception exists in 2023-24
only (§6(j)(1)(iii)), and §2(e)(5) — directly beneath the table on p. 215 —
exempts rows F–J executed during 2023-24 from creating a 2023-24 ceiling. The
sole season it can fire in is the season it is exempted in. The only residue is
§2(e)(2)(ii): used between the end of the 2023-24 Regular Season and 30 June
2024, it could bind 2024-25. Worth confirming the reading, not the value.

| ✅ | Also | Detail | Citation |
|---|---|---|---|
| ✅ | 2023-24 carve-out | Rows **F–J** executed during 2023-24 create **no** 2023-24 ceiling | §2(e)(5), p. 215 |
| ✅ | Mechanism | A team engaging in a listed transaction may not exceed that row's apron level **for the remainder of the Salary Cap Year** | §2(e)(2)(i)(B), p. 211 |
| ✅ | Timing | Rows **E–J** executed after the Regular Season bind the **following** Salary Cap Year | §2(e)(2)(ii), p. 212 |

## 3. Aggregation restrictions — Article VII §6(j)(4), p. 266

| ✅ | Constant | Value encoded | Citation |
|---|---|---|---|
| ✅ | Two-month bar | A contract acquired via an Exception may not be aggregated for **two months** | §6(j)(4)(i) |
| ✅ | Carve-out | Acquired on or before **December 16** → bar lifts from the day before the trade deadline | §6(j)(4)(i) |
| ✅ | Three-player rule | Extra restriction outside the **December 15 → trade deadline** window | §6(j)(4)(ii) |

## 4. Over-38 Rule — Article VII §3(a)(2), p. 222

| ✅ | Constant | Value encoded | Note |
|---|---|---|---|
| ✅ | Trigger | **four or more Seasons** AND one commencing after the player reaches 38 | Both halves required — a three-year deal never qualifies |

## 5. Maximum Annual Salary — Article II §7(a), pp. 59–61

Each tier reads **"the greater of X% of the Salary Cap, or 105% of the Salary for
the final Season of the player's prior Contract."** The 105% alternative is
routinely dropped from summaries and raises the maximum for anyone coming off a
large deal.

| ✅ | Tier | Standard | Higher | Who qualifies for the higher figure |
|---|---|---|---|---|
| ✅ | **fewer than 7** YOS (so 0–6, not 1–6) | **25%** | **30%** | **"5th Year Eligible Players"** only — 4 YOS as of the June 30 following their last contract season |
| ✅ | **7 to 9** YOS | **30%** | **35%** | **8 or 9** YOS only, *and* rendered with the team he first signed with (or changed teams only by trade in his first four cap years) |
| ✅ | **10 or more** YOS | **35%** | — | already top tier |

| ✅ | Constant | Value encoded |
|---|---|---|
| ✅ | Prior-salary alternative | **105%** of the prior contract's final-Season Salary, in every tier |
| ✅ | Qualifying honours | All-NBA (1st/2nd/3rd), **Defensive Player of the Year**, or **MVP** |
| ✅ | All-NBA / DPOY window | immediately preceding Season, **or two of the preceding three** |
| ✅ | MVP window | **one of the preceding three** Seasons |
| ✅ | All-Star | **not** qualifying — deliberately excluded |
| ✅ | 5th-year timing | criteria measured **as of the July 1 following the player's fourth Season** |
| ✅ | Designated veteran timing | criteria measured **at the time the Contract is executed** |
| ✅ | Rookie extension tiers | All-NBA 2nd **27%**, All-NBA 1st **28%**, MVP **30%** (§7(d), p. 65) |

**Two traps worth confirming.** Meeting the Higher Max Criteria is *not*
sufficient on its own — each tier has a separate eligibility gate, so a 7-YOS
player with an All-NBA selection is still capped at 30%. And the higher figure
applies to a subset of the tier, not the whole tier.

## 5b. Apron restrictions are derived, not listed — Art. VII §2(e)(2)(i)(A), p. 211

Worth a look because it contradicts every summary. **The CBA contains no list of
apron restrictions.** They fall out of one sentence: a team may not engage in a
Transaction Restrictions Table row if its Apron Team Salary *immediately
following* would exceed that row's Applicable Apron Level.

| ☐ | Claim | Check |
|---|---|---|
| ☐ | There is no enumerated "second apron restrictions" list in the document | Confirm you cannot find one |
| ☐ | Rows **A–F** close above the first apron | §2(e)(4) plus §2(e)(2)(i)(A) |
| ☐ | Rows **H–K** close above the second apron | Same |
| ☐ | "Cannot aggregate salaries" = row **H** | Aggregated Standard TPE |
| ☐ | "Cannot send cash" = row **I** | Pays cash in a trade |
| ☐ | "Cannot use the taxpayer MLE" = row **K** | Taxpayer MLE |
| ☐ | The test is salary **after** the transaction, not before | §2(e)(2)(i)(A) wording |
| ☐ | §6(m) non-aggregation applies to **all** teams, not just apron teams | Often miscited as an apron rule |

## 6. NBA Constitution and By-Laws (2024) — a different document

Not collective bargaining. Cited separately so a verdict says which document it
rests on.

| ☐ | By-Law | Rule encoded |
|---|---|---|
| ☐ | **7.03**, p. 85 | No Member may **sell** first-round pick rights for cash or its equivalent |
| ☐ | **7.03**, p. 85 | No trade whose result **"may be"** to leave the Member without first-round picks in any **two consecutive** future Drafts |
| ☐ | 7.03 reading | "without first-round pick**s**" — *any* first satisfies it, including another team's |
| ☐ | 7.03 reading | **"may be"** — a protected pick that might not convey counts as possibly absent |
| ☐ | **4.01(a)**, p. 69 | Deadline is 3 p.m. eastern on the **second Thursday prior** to that Season's All-Star Game |
| ☐ | 4.01(a) | Closed from the deadline until the day after the last Regular Season Game |
| ☐ | 4.01(a) | Postseason teams may not assign a Player on the Postseason Roster until eliminated; nothing moves during the Moratorium Period |
| ☐ | **Not found** | The seven-Drafts-ahead horizon is in neither document. Confirm you agree it is absent. |

**This is the section to review for 3.16.** The two readings of 7.03 are
judgment calls on wording rather than transcription, so they are where a second
opinion is worth most.

## What to do with a mismatch

Every one of these has a test asserting it, so a correction is a one-line change
plus a failing test that proves the fix.

## History

| Date | Outcome |
|---|---|
| 2026-09-29 | Full pass. Row G reclassified as unreachable; Maximum Annual Salary corrected (tier boundary 0–6 not 1–6, 10+ tier added, 105% alternative added, eligibility gates separated from the criteria). Everything else confirmed as transcribed. |
