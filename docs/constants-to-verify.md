# Constants to verify

Values transcribed from the CBA into `packages/engine`. I can transcribe
accurately but cannot independently confirm that I did — a second reader is the
only real control, and each of these propagates into every verdict the engine
gives.

Roughly half an hour against `data/cba/nba-cba-2023.pdf`. Page numbers are the
PDF's own.

Tick a row when you've checked it against the document.

## 1. Salary matching — Article VII §6(j)(1), pp. 264–266

**The highest-priority block.** The commonly cited "125% + $100,000" is the
**2017** CBA. If the values below are wrong, every matching verdict is wrong.

| ☐ | Constant | Value encoded | Citation |
|---|---|---|---|
| ☐ | Flat allowance | **$250,000** (not $100,000) | §6(j)(1) |
| ☐ | Standard TPE | **100%** of pre-trade salary + allowance | §6(j)(1)(i), p. 264 |
| ☐ | Aggregated Standard | **100%** of aggregated salaries + allowance | §6(j)(1)(ii), p. 264 |
| ☐ | Transition TPE | **110%** + allowance, **2023-24 only** | §6(j)(1)(iii), p. 265 |
| ☐ | Expanded TPE | greater of **(y)** lesser of [200% + allowance] and [100% + $7.5m × cap_now ÷ cap_2023-24], or **(z)** 125% + allowance | §6(j)(1)(iv), p. 265 |
| ☐ | Room absorption | cap room + allowance; **may not** be combined with (i)–(iv) | §6(j)(1)(v), p. 265 |
| ☐ | Allowance removal | allowance → **$0** if post-assignment Apron Team Salary would exceed the First Apron Level | §6(j)(3), p. 266 |
| ☐ | Expanded base year | $7.5m scales against the **2023-24** cap ($136,021,000) | §6(j)(1)(iv)(y)(B) |

## 2. Transaction Restrictions Table — Article VII §2(e)(4), pp. 214–215

Eleven rows, not the handful usually cited. Rows A–G set a **first** apron
ceiling; H–K a **second**.

| ☐ | Row | Transaction | Apron |
|---|---|---|---|
| ☐ | A | Bi-annual Exception | First |
| ☐ | B | Non-Taxpayer MLE | First |
| ☐ | C | Acquiring a player on a §8(e)(1) contract (sign-and-trade) | First |
| ☐ | D | In-season signing of a waived player paid above the Non-Taxpayer MLE | First |
| ☐ | E | Expanded Traded Player Exception | First |
| ☐ | F | Standard TPE used after the Regular Season in which it arose | First |
| ☐ | G | Transition Traded Player Exception | First *(see note)* |
| ☐ | H | Aggregated Standard TPE | **Second** |
| ☐ | I | **Paying cash** to another team in a trade | **Second** |
| ☐ | J | TPE arising from a signed-and-traded contract | **Second** |
| ☐ | K | Taxpayer MLE | **Second** |

**Note on row G.** The apron level is transcribed correctly, but the row is
unreachable for any season we model. The Transition exception exists in 2023-24
only (§6(j)(1)(iii)), and §2(e)(5) — directly beneath the table on p. 215 —
exempts rows F–J executed during 2023-24 from creating a 2023-24 ceiling. The
sole season it can fire in is the season it is exempted in. The only residue is
§2(e)(2)(ii): used between the end of the 2023-24 Regular Season and 30 June
2024, it could bind 2024-25. Worth confirming the reading, not the value.

| ☐ | Also | Detail | Citation |
|---|---|---|---|
| ☐ | 2023-24 carve-out | Rows **F–J** executed during 2023-24 create **no** 2023-24 ceiling | §2(e)(5), p. 215 |
| ☐ | Mechanism | A team engaging in a listed transaction may not exceed that row's apron level **for the remainder of the Salary Cap Year** | §2(e)(2)(i)(B), p. 211 |
| ☐ | Timing | Rows **E–J** executed after the Regular Season bind the **following** Salary Cap Year | §2(e)(2)(ii), p. 212 |

## 3. Aggregation restrictions — Article VII §6(j)(4), p. 266

| ☐ | Constant | Value encoded | Citation |
|---|---|---|---|
| ☐ | Two-month bar | A contract acquired via an Exception may not be aggregated for **two months** | §6(j)(4)(i) |
| ☐ | Carve-out | Acquired on or before **December 16** → bar lifts from the day before the trade deadline | §6(j)(4)(i) |
| ☐ | Three-player rule | Extra restriction outside the **December 15 → trade deadline** window | §6(j)(4)(ii) |

## 4. Over-38 Rule — Article VII §3(a)(2), p. 222

| ☐ | Constant | Value encoded | Note |
|---|---|---|---|
| ☐ | Trigger | **four or more Seasons** AND one commencing after the player reaches 38 | Both halves required — a three-year deal never qualifies |

## 5. Higher Max Criteria — Article II §7, pp. 60–61

| ☐ | Constant | Value encoded |
|---|---|---|
| ☐ | Qualifying honours | All-NBA (1st/2nd/3rd), **Defensive Player of the Year**, or **MVP** |
| ☐ | All-NBA / DPOY window | immediately preceding Season, **or two of the preceding three** |
| ☐ | MVP window | **one of the preceding three** Seasons |
| ☐ | All-Star | **not** a qualifying honour — deliberately excluded |
| ☐ | 4 YOS tier | 25% → up to **30%** of the cap |
| ☐ | 8–9 YOS tier | 30% → up to **35%**, with continuous-team tenure |
| ☐ | Rookie extension tiers | All-NBA 2nd **27%**, All-NBA 1st **28%**, MVP **30%** (Art. II §7(d), p. 65) |

## What to do with a mismatch

Open an issue or tell me the row. Every one of these has a test asserting it, so
a correction is a one-line change plus a failing test that proves the fix.
