# Scrapers

Two scripts, both stdlib-only:

- `fanspo_scrape.py` — team cap sheets (rosters, cap holds, draft picks, trade exceptions)
- `bbref_awards.py` — All-NBA / DPOY / MVP from Basketball-Reference
- `bbref_contracts.py` — multi-year salaries, per-year options, signing dates
- `spotrac_archive.py` — guarantee dates, extension-eligibility dates, via the Wayback Machine
- `bbref_roster.py` — years of service (the roster "Exp" column) and birth dates

---

# Fanspo cap-sheet scraper

Pulls the embedded `__NEXT_DATA__` Apollo GraphQL cache out of each team's Fanspo
cap-sheet page and normalizes it into one CSV per type.

Stdlib only — no `pip install`.

```bash
python3 fanspo_scrape.py                  # all 30 teams -> ./out
python3 fanspo_scrape.py --teams 1,2,3    # subset
python3 fanspo_scrape.py --force          # ignore the raw HTML cache
python3 fanspo_scrape.py --delay 2.5      # slower
```

Raw HTML is cached in `out/raw/team_NN.html`, so re-runs re-parse without
re-fetching. Use `--force` to refresh.

## How the URL works

`https://fanspo.com/nba/cap-sheets/{slug}/{id}` — **the slug is decorative.**
`/cap-sheets/hawks/2` returns the Celtics. Only the trailing integer selects the
team, so the scraper iterates ids 1–30 with a constant slug.

## Output

| File | Rows | Contents |
|---|---|---|
| `team_profile.csv` | 30 | Record, SRS, pace, off/def rating, coach, arena — 2026-27 |
| `team_payroll_player.csv` | 663 | Name, position, baseSalary, capHit, payrollType |
| `team_cap_hold.csv` | 213 | capHit, qualifyingOfferAmount, **rightType** (Bird / Early Bird / Non-Bird / …) |
| `draft_pick.csv` | 616 | Year, round, from/to, and **full protection prose** in `details` |
| `trade_exception.csv` | 478 | Amount, expiration, type, isActive — see caveats |
| `player_info.csv` | 461 | **birthDate**, draft year/round/pick, nbaDebut, height/weight, college |
| `player.csv` | 654 | Identity, fromYear/toYear, refs to info and lebron |
| `player_transaction.csv` | 814 | Dated transaction log with type and description |
| `salary_cap_figure.csv` | 24 | Cap, tax, apron, apronTwo, all three MLEs, BAE — **2011-12 → 2034-35** |
| `player_lebron.csv` | 429 | LEBRON metric and offensive archetype |
| `team_staff.csv` | 504 | Coaching and front office |
| `all.json` | — | Everything, unsplit |
| `manifest.json` | — | Per-page provenance: URL, sha256, timestamp, object counts |

Every row carries `_source_team_ids` — a pipe-joined list of which team pages the
object appeared on. Pages carry league-wide objects (all 30 team profiles, shared
cap figures), so this is both the dedupe key and, in one case below, the only
correct way to attribute an object to a team.

## Caveats — read before using this data

**1. Current season only.** The initial HTML payload carries a single `capHit`
per player for 2026-27. The multi-year salary grid, per-year option flags, and
guarantee status render **client-side** and are not in this data. Getting them
needs headless rendering (Playwright) or the underlying API.

Still outstanding after this scrape, per `division-of-labor.md` §4.1:

- Option type per contract year (team / player / ETO)
- Guarantee status per year and guarantee dates
- Trade kicker %
- No-trade clauses
- Years of service (approximable from `player_info.nbaDebut` / `player.fromYear`)
- Awards — All-NBA / DPOY / MVP (§4.2, B7). Not on Fanspo at all.

**2. `trade_exception.fromTeamId` is the counterparty, not the holder.**
It disagrees with the source page on 407 of 478 rows. Example: a TPE appearing
only on the Hawks page carries `fromTeamId=30` and player Trae Young — that is
the team the player went *to*, not the team holding the exception. **Attribute
TPEs to the team via `_source_team_ids`, never via `fromTeamId`.**

**3. `trade_exception.isActive` is stale.** 44 of the 98 rows flagged
`isActive=True` have expiration dates already in the past, the earliest being
2025-06-30. Recompute expiry against the date you care about; don't trust the flag.

**4. Offseason rosters are incomplete.** Active roster counts run 9–16 per team
because this is a 2026-27 offseason snapshot. That's the real state of the world,
not a scraper bug — but it means roster-minimum checks (task 2.16) will fire
against this data.

**5. Draft picks are 2027–2033 only**, 616 rows across both rounds. Swap rights
appear as their own entries, which is why the count exceeds 30 teams × 7 years × 2.

## Provenance

`manifest.json` records the fetch timestamp, URL, and a content hash per page.
Task 1.13 wants this carried through into the domain model, and 9.7 wants it
visible in the UI — don't drop it during import.


---

# Basketball-Reference awards scraper

```bash
python3 bbref_awards.py                      # 2023-24 forward -> out/awards.csv
python3 bbref_awards.py --from-season 2019   # more history
python3 bbref_awards.py --force              # refetch
```

Collects **only** the three awards that constitute the CBA's **Higher Max
Criteria** (Article II, Section 7, pp. 60–61): All-NBA 1st/2nd/3rd team,
Defensive Player of the Year, and MVP. Those three gate the 30% and 35% max
tiers and the rookie-scale extension escalators.

**All-Star is deliberately excluded.** It is not part of the Higher Max Criteria;
it belongs to a separate defined term ("Generally Recognized League Honors",
Article I(cc)) governing incentive compensation. See `division-of-labor.md` §4.2.

### Output: `out/awards.csv`

Tidy long format — one row per (player, season, award) — which is the shape
task 7.4's eligibility check wants to query.

| Column | Notes |
|---|---|
| `season` | Basketball-Reference form, `2023-24` |
| `season_id` | Fanspo form, `2023-2024` — join key |
| `award` | `All-NBA` / `DPOY` / `MVP` |
| `tier` | `1st` / `2nd` / `3rd` for All-NBA, else `Winner` |
| `player_name` | |
| `bbref_id` | e.g. `jokicni01` |
| `position` | All-NBA only |

51 rows covering 2023-24 → 2025-26 (45 All-NBA + 3 DPOY + 3 MVP). That window is
exactly what Higher Max Criteria needs for 2026-27 decisions: the immediately
preceding season plus two of the preceding three.

**`bbref_id` joins directly** to the trailing id column in
`data/player_yearly_salary.csv` — 28 of 29 award winners match.

### Politeness

`/awards/` is not disallowed by `robots.txt`. The script honors the site's
declared `Crawl-delay: 3` and caches raw HTML in `out/raw/`, so it makes three
requests total on a cold run and zero thereafter.


---

# Basketball-Reference contracts scraper

```bash
python3 bbref_contracts.py              # all 30 teams -> out/
python3 bbref_contracts.py --teams ATL,BOS
python3 bbref_contracts.py --force      # refetch
```

One page per team (`/contracts/{TM}.html`). Closes four `division-of-labor.md`
§4.1 gaps: **multi-year salaries, per-year option types, guaranteed remaining,
and signing dates.**

### Output

| File | Rows | Contents |
|---|---|---|
| `contracts.csv` | 1,124 | One row per player-season: `team`, `bbref_id`, `player_name`, `season`, `season_id`, `salary`, `option_type` |
| `contract_totals.csv` | 564 | Per player: `age`, `guaranteed_remaining` (438 populated) |
| `contract_notes.csv` | 567 | `signed_date`, `contract_years`, `contract_value`, `is_extension`, `option_seasons_in_note`, `option_exercised_date`, `traded_from`, `traded_date`, raw `note` |

**365 option-years**: 284 team, 81 player. Season coverage runs 2026-27 (497
rows) through 2031-32 (3 rows). Signing dates on 349 of 567 notes — the
remainder are two-way, minimum, and draft-pick notes with no `Signed N-yr/$X`
phrasing. `bbref_id` joins to `awards.csv` (28/29) and to the trailing id column
in `data/player_yearly_salary.csv`.

### Two independent option signals — use the union

Option type is recovered twice: from the CSS class on the salary cell
(`salary-tm` / `salary-pl` / `salary-et`) and from prose in the notes table
("2028-29 is a player option"). Both are emitted.

Across all 30 teams: **137 agree, 0 disagree.** But neither is complete on its own:

- **228 CSS-only** — the notes simply don't mention most options
- **11 prose-only** — of which **6 are options on seasons that *are* in the salary
  grid but carry no CSS class** (Donovan Mitchell 2027-28, Aaron Gordon 2027-28,
  Damian Lillard 2026-27, Bradley Beal 2026-27, Cole Anthony 2026-27, Micah
  Potter 2026-27). The other 5 reference seasons outside the six-year grid.

**So take the union of `option_type` and `option_seasons_in_note`, not either
alone.** The zero-disagreement rate means the union is safe; the 6 CSS misses
mean it's necessary.

### Not covered

Guarantee **dates**, partial guarantee amounts, trade kickers, and incentives.
Those live on the archived Spotrac cap pages — the two sources are
complementary. See `division-of-labor.md` §4.1.

### Politeness

`/contracts/` is not disallowed by `robots.txt`. Honors the declared
`Crawl-delay: 3` and caches raw HTML in `out/raw/`, so a cold run is 30
requests and re-runs are zero.


---

# Spotrac archive scraper

```bash
python3 spotrac_archive.py               # year 2026, all teams
python3 spotrac_archive.py --year 2024   # historical
python3 spotrac_archive.py --refresh-cdx
```

Reads archived Spotrac cap sheets through the Wayback Machine. Spotrac blocks
both the archiver (from ~July 2026) and direct automated access, so the archive
is the only route.

Tables are matched by **header signature, not position** — Spotrac's table
order varies by team and page vintage, so positional indexing fails silently.

### Result of the 2026 run: 30/30 teams

| File | Rows |
|---|---|
| `spotrac_decisions.csv` | 773 |
| `spotrac_roster.csv` | 392 |
| `spotrac_cap_holds.csv` | 262 |
| `spotrac_trade_exceptions.csv` | 77 |

`spotrac_decisions.csv` is the valuable one — **~270 options, ~200 qualifying
offers, ~200 extension-eligibility dates, ~105 guarantee dates**, each with a
decision deadline, season, and value where applicable.

Chicago initially failed and was recovered by two fixes worth knowing about:
Spotrac has used two year-bearing URL forms (`/cap/_/year/2026` and the older
`/cap/2026/`) and only the first was ranked; and a failed archive query was
being cached as an empty result, so the team was permanently skipped. Both are
fixed. The URL-form fix matters most for **historical runs**, where the older
form is far more common.

### Read the snapshot dates before using this

**Snapshots span 2025-06-23 to 2026-07-18** — a 13-month range across 22
distinct dates. `snapshot_date` is stamped on every row. This is a set of
point-in-time observations, **not one coherent league state.**

Because Spotrac's decision calendar is forward-looking, 25 of the 29 teams still
describe the **2026-27** season despite the date spread. Four do not:

| Team | Season the page describes |
|---|---|
| dallas-mavericks | 2027-28 |
| portland-trail-blazers | 2025-26 |
| sacramento-kings | 2025-26 |
| san-antonio-spurs | 2025-26 |

Filter on `season` rather than assuming a uniform league year.

### Fields this does NOT deliver, despite the column existing

**Trade kickers are not obtainable here.** The roster table renders a "Trade
Bonus Proration" column in all 33 parsed tables, and it is **empty in all 384
rows** across all 29 teams. Verified against the raw HTML — this is genuine
absence in the archived pages, not a parse failure. Spotrac evidently populates
it client-side or only when logged in.

**Incentives are near-empty**: `incentives_likely` 6/384, `incentives_unlikely`
30/384. Plausibly genuine sparsity (few contracts carry them) rather than a
parsing gap, but treat as unreliable.

Populated as expected: `cap_hit` 371/384, `guaranteed` 317/384, cap holds with
Bird rights, and trade exceptions with `original` vs `available`.


---

# Basketball-Reference roster scraper (years of service)

```bash
python3 bbref_roster.py              # 2025-26 season, all teams
python3 bbref_roster.py --year 2025  # historical
```

**661 players across 30 teams, every row with `years_experience` and
`birth_date`.** Replaces the derived YOS approximation, which diverged from the
real figure for two-way, G-League and injury seasons.

### Convention — read before using

`years_experience` on the `{YEAR}` page counts seasons **completed before** that
season; rookies are 0. A player drafted in 2019 shows `6` on the 2025-26 page.

For 2026-27 eligibility, use the 2027 page when it exists, or add 1 for players
who were on a roster in 2025-26. `season` is emitted on every row so this
adjustment is explicit rather than assumed.

Row count exceeds unique players (661 rows, 582 ids) because players traded
mid-season appear on both rosters — correct for a season roster, but dedupe on
`bbref_id` before joining. `birth_date` cross-checks Fanspo's `player_info`.
