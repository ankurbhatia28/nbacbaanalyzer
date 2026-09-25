#!/usr/bin/env python3
"""
Basketball-Reference contracts scraper.

One page per team (/contracts/{TM}.html) gives a six-season salary grid with
per-year option annotations, plus a notes table carrying signing dates.

Closes these division-of-labor.md section 4.1 gaps:
  - multi-year salary per player
  - option type per contract year (team / player / early termination)
  - guaranteed remaining
  - signing dates (task 2.13, the trade restriction calendar)

Does NOT carry guarantee dates, partial guarantee amounts, trade kickers, or
incentives. Those come from the archived Spotrac cap pages -- the two sources
are complementary, not redundant.

Option type is recovered two independent ways: the CSS class on the salary
cell (salary-tm / salary-pl / salary-et) and the prose in the notes table
("2028-29 is a player option"). Both are emitted so they can be cross-checked;
disagreement is a parser bug worth catching.

Respects the site's declared Crawl-delay of 3s. /contracts/ is not disallowed
by robots.txt. Stdlib only.

Usage:
    python3 bbref_contracts.py            # all 30 teams -> ./out
    python3 bbref_contracts.py --teams ATL,BOS
    python3 bbref_contracts.py --force    # ignore the raw HTML cache
"""

from __future__ import annotations

import argparse
import csv
import gzip
import html as html_mod
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

BASE = "https://www.basketball-reference.com/contracts/{team}.html"
CRAWL_DELAY = 3.0

# Basketball-Reference's own abbreviations (BRK not BKN, CHO not CHA, PHO not PHX).
TEAMS = [
    "ATL",
    "BOS",
    "BRK",
    "CHO",
    "CHI",
    "CLE",
    "DAL",
    "DEN",
    "DET",
    "GSW",
    "HOU",
    "IND",
    "LAC",
    "LAL",
    "MEM",
    "MIA",
    "MIL",
    "MIN",
    "NOP",
    "NYK",
    "OKC",
    "ORL",
    "PHI",
    "PHO",
    "POR",
    "SAC",
    "SAS",
    "TOR",
    "UTA",
    "WAS",
]

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

OPTION_CLASS = {
    "salary-tm": "team",
    "salary-pl": "player",
    "salary-et": "early_termination",
}

TAG_RE = re.compile(r"<[^>]+>")
ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL)
CELL_RE = re.compile(r"<(t[hd])([^>]*)data-stat=\"([^\"]+)\"([^>]*)>(.*?)</\1>", re.DOTALL)
CSK_RE = re.compile(r"csk=\"([^\"]*)\"")
PLAYER_HREF_RE = re.compile(r"/players/\w/(\w+)\.html")
CLASS_RE = re.compile(r"class=\"([^\"]*)\"")

NOTE_SIGNED_RE = re.compile(r"Signed\s+(\d+)-yr/\$([\d.]+)([MK])\s+([^.]*?)(\w+\s+\d+,\s+\d{4})")
NOTE_OPTION_RE = re.compile(r"(\d{4}-\d{2})\s+is\s+a\s+(team|player)\s+option", re.I)
NOTE_TRADE_RE = re.compile(r"Traded from (\w+) to (\w+) (\w+\s+\d+,\s+\d{4})")
NOTE_EXERCISED_RE = re.compile(r"Option exercised (\w+\s+\d+,\s+\d{4})")


def fetch(url: str, retries: int = 3) -> str:
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
                return raw.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            last = e
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
        if attempt < retries - 1:
            wait = CRAWL_DELAY * (attempt + 2)
            print(f"      retry {attempt + 1} in {wait:.0f}s ({last})")
            time.sleep(wait)
    raise RuntimeError(f"failed: {url} ({last})")


def txt(fragment: str) -> str:
    return re.sub(r"\s+", " ", html_mod.unescape(TAG_RE.sub(" ", fragment))).strip()


def money(raw_text: str, csk: str | None) -> int | None:
    if csk and csk.lstrip("-").isdigit():
        return int(csk)
    digits = re.sub(r"[^\d]", "", raw_text)
    return int(digits) if digits else None


def parse_contracts(page_html: str, team: str) -> tuple:
    m = re.search(r'<table[^>]*id="contracts".*?</table>', page_html, re.DOTALL)
    if not m:
        raise ValueError("contracts table not found")
    table = m.group(0)
    rows = ROW_RE.findall(table)

    # Header row maps y1..y6 -> a season label like "2026-27".
    seasons: dict = {}
    for row in rows:
        for c in CELL_RE.finditer(row):
            stat = c.group(3)
            if re.fullmatch(r"y\d+", stat) and 'scope="col"' in (c.group(2) + c.group(4)):
                label = txt(c.group(5))
                if re.fullmatch(r"\d{4}-\d{2}", label):
                    seasons[stat] = label
        if seasons:
            break
    if not seasons:
        raise ValueError("could not map season columns")

    salary_rows, total_rows = [], []
    for row in rows:
        cells = {
            c.group(3): (
                txt(c.group(5)),
                CSK_RE.search(c.group(2) + c.group(4)),
                CLASS_RE.search(c.group(2) + c.group(4)),
            )
            for c in CELL_RE.finditer(row)
        }
        player = cells.get("player")
        if not player or not player[1]:
            continue  # header or summary row
        bbref_id = player[1].group(1)
        name = player[0]
        if not bbref_id or name.lower() in ("player", "team totals"):
            continue
        age = cells.get("age_today", ("", None, None))[0] or None

        for stat, season in seasons.items():
            cell = cells.get(stat)
            if not cell:
                continue
            value, csk, cls = cell
            classes = cls.group(1).split() if cls else []
            if "iz" in classes and not value:
                continue
            amount = money(value, csk.group(1) if csk else None)
            if amount is None:
                continue
            option = next((OPTION_CLASS[c] for c in classes if c in OPTION_CLASS), None)
            salary_rows.append(
                {
                    "team": team,
                    "bbref_id": bbref_id,
                    "player_name": name,
                    "season": season,
                    "season_id": f"{season[:4]}-{int(season[:4]) + 1}",
                    "salary": amount,
                    "option_type": option,
                }
            )

        gtd = cells.get("remain_gtd")
        total_rows.append(
            {
                "team": team,
                "bbref_id": bbref_id,
                "player_name": name,
                "age": age,
                "guaranteed_remaining": money(gtd[0], gtd[1].group(1) if gtd and gtd[1] else None)
                if gtd
                else None,
            }
        )
    return salary_rows, total_rows


def parse_notes(page_html: str, team: str) -> list:
    m = re.search(r'<table[^>]*id="payroll-notes".*?</table>', page_html, re.DOTALL)
    if not m:
        return []
    out = []
    for row in ROW_RE.findall(m.group(0)):
        cells = list(CELL_RE.finditer(row))
        if not cells:
            continue
        player_cell = next((c for c in cells if c.group(3) == "player"), None)
        if not player_cell:
            continue
        raw_player = player_cell.group(5)
        href = PLAYER_HREF_RE.search(raw_player)
        csk = CSK_RE.search(player_cell.group(2) + player_cell.group(4))
        bbref_id = href.group(1) if href else (csk.group(1) if csk else None)
        name = txt(raw_player)
        if not bbref_id or name.lower() in ("player", ""):
            continue
        note = " ".join(txt(c.group(5)) for c in cells if c.group(3) != "player").strip()
        if not note:
            continue

        signed = NOTE_SIGNED_RE.search(note)
        mult = {"M": 1_000_000, "K": 1_000}
        traded = NOTE_TRADE_RE.search(note)
        exercised = NOTE_EXERCISED_RE.search(note)
        out.append(
            {
                "team": team,
                "bbref_id": bbref_id,
                "player_name": name,
                "signed_date": signed.group(5) if signed else None,
                "contract_years": int(signed.group(1)) if signed else None,
                "contract_value": (
                    int(float(signed.group(2)) * mult[signed.group(3)]) if signed else None
                ),
                "is_extension": ("extension" in signed.group(4).lower()) if signed else None,
                "option_seasons_in_note": "|".join(
                    f"{s}:{k.lower()}" for s, k in NOTE_OPTION_RE.findall(note)
                )
                or None,
                "option_exercised_date": exercised.group(1) if exercised else None,
                "traded_from": traded.group(1) if traded else None,
                "traded_date": traded.group(3) if traded else None,
                "note": note,
            }
        )
    return out


def write_csv(path: str, rows: list, cols: list) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="Scrape NBA contracts from Basketball-Reference.")
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--out", default=os.path.join(here, "out"))
    ap.add_argument("--teams", default="")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    teams = [t.strip().upper() for t in args.teams.split(",") if t.strip()] or TEAMS
    raw_dir = os.path.join(args.out, "raw")
    os.makedirs(raw_dir, exist_ok=True)

    salaries, totals, notes, failures = [], [], [], []
    net_calls = 0

    for i, team in enumerate(teams, 1):
        path = os.path.join(raw_dir, f"bbref_contracts_{team}.html")
        if os.path.exists(path) and not args.force:
            page = open(path, encoding="utf-8").read()
            src = "cache"
        else:
            if net_calls:
                time.sleep(CRAWL_DELAY)
            try:
                page = fetch(BASE.format(team=team))
            except Exception as e:
                print(f"[{i:2d}/{len(teams)}] {team}  !! {e}")
                failures.append({"team": team, "error": str(e)[:120]})
                continue
            net_calls += 1
            with open(path, "w", encoding="utf-8") as f:
                f.write(page)
            src = "network"

        try:
            s, t = parse_contracts(page, team)
            n = parse_notes(page, team)
        except ValueError as e:
            print(f"[{i:2d}/{len(teams)}] {team}  !! parse: {e}")
            failures.append({"team": team, "error": f"parse: {e}"})
            continue

        salaries += s
        totals += t
        notes += n
        opts = sum(1 for r in s if r["option_type"])
        print(
            f"[{i:2d}/{len(teams)}] {team} ({src:7s}) {len(t):2d} players, "
            f"{len(s):3d} player-seasons, {opts:2d} options, {len(n):2d} notes"
        )

    os.makedirs(args.out, exist_ok=True)
    write_csv(
        os.path.join(args.out, "contracts.csv"),
        salaries,
        ["team", "bbref_id", "player_name", "season", "season_id", "salary", "option_type"],
    )
    write_csv(
        os.path.join(args.out, "contract_totals.csv"),
        totals,
        ["team", "bbref_id", "player_name", "age", "guaranteed_remaining"],
    )
    write_csv(
        os.path.join(args.out, "contract_notes.csv"),
        notes,
        [
            "team",
            "bbref_id",
            "player_name",
            "signed_date",
            "contract_years",
            "contract_value",
            "is_extension",
            "option_seasons_in_note",
            "option_exercised_date",
            "traded_from",
            "traded_date",
            "note",
        ],
    )

    manifest = {
        "scraped_at": datetime.now(UTC).isoformat(),
        "source": "basketball-reference.com/contracts/",
        "crawl_delay_s": CRAWL_DELAY,
        "teams_requested": len(teams),
        "teams_ok": len(teams) - len(failures),
        "failures": failures,
        "rows": {
            "contracts": len(salaries),
            "contract_totals": len(totals),
            "contract_notes": len(notes),
        },
        "not_covered": [
            "guarantee dates",
            "partial guarantee amounts",
            "trade kickers",
            "incentives (likely/unlikely)",
        ],
    }
    with open(os.path.join(args.out, "contracts_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"\n  contracts.csv        {len(salaries):5d} player-seasons")
    print(f"  contract_totals.csv  {len(totals):5d} players")
    print(f"  contract_notes.csv   {len(notes):5d} notes")
    if failures:
        print(f"  FAILURES: {[f['team'] for f in failures]}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
