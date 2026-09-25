#!/usr/bin/env python3
"""
Basketball-Reference team roster scraper -- years of service.

Closes the last derived-not-authoritative field in division-of-labor.md 4.1.
Until now YOS was approximated from nbaDebut / draftYear, which diverges for
two-way, G-League and injury seasons. Basketball-Reference publishes it
directly as the roster "Exp" column.

CONVENTION, which matters for the CBA rules that key off YOS:
  years_experience on the {YEAR} page = seasons COMPLETED BEFORE that season.
  A player drafted in 2019 shows exp=6 on the 2025-26 page.
So for 2026-27 eligibility, use the 2027 page if it exists, else 2026 + 1 for
players who were on a roster that season. The season is emitted on every row
so the consumer can make that adjustment explicitly rather than guessing.

Also carries birth_date, which cross-checks Fanspo's player_info.

Stdlib only. Honors the declared Crawl-delay of 3s; /teams/ is not disallowed.

Usage:
    python3 bbref_roster.py               # 2026 season, all teams
    python3 bbref_roster.py --year 2025   # historical
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

BASE = "https://www.basketball-reference.com/teams/{team}/{year}.html"
CRAWL_DELAY = 3.0
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

TAG_RE = re.compile(r"<[^>]+>")
CELL_RE = re.compile(r'data-stat="([^"]+)"[^>]*>(.*?)</t[hd]>', re.DOTALL)
PID_RE = re.compile(r"/players/\w/(\w+)\.html")


def txt(s: str) -> str:
    return re.sub(r"\s+", " ", html_mod.unescape(TAG_RE.sub(" ", s))).strip()


def fetch(url: str, retries: int = 3) -> str:
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml",
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
            time.sleep(CRAWL_DELAY * (attempt + 2))
    raise RuntimeError(f"failed: {url} ({last})")


def parse_roster(page: str, team: str, year: int) -> list:
    m = re.search(r'<table[^>]*id="roster".*?</table>', page, re.DOTALL)
    if not m:
        raise ValueError("roster table not found")
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(0), re.DOTALL):
        if 'data-stat="player"' not in row:
            continue
        cells = {k: txt(v) for k, v in CELL_RE.findall(row)}
        pid = PID_RE.search(row)
        name = cells.get("player", "")
        if not pid or not name or name.lower() == "player":
            continue
        exp_raw = cells.get("years_experience", "")
        # B-R writes "R" for rookies (zero prior seasons)
        exp = 0 if exp_raw.upper() == "R" else (int(exp_raw) if exp_raw.isdigit() else None)
        out.append(
            {
                "team": team,
                "season": f"{year - 1}-{str(year)[2:]}",
                "bbref_id": pid.group(1),
                "player_name": name,
                "years_experience": exp,
                "birth_date": cells.get("birth_date") or None,
                "position": cells.get("pos") or None,
                "height": cells.get("height") or None,
                "weight": cells.get("weight") or None,
                "college": cells.get("college") or None,
            }
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Scrape NBA rosters (years of experience).")
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--out", default=os.path.join(here, "out"))
    ap.add_argument(
        "--year", type=int, default=2026, help="B-R season-ending year (2026 = the 2025-26 season)"
    )
    ap.add_argument("--teams", default="")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    teams = [t.strip().upper() for t in args.teams.split(",") if t.strip()] or TEAMS
    raw_dir = os.path.join(args.out, "raw")
    os.makedirs(raw_dir, exist_ok=True)

    rows, failures, net = [], [], 0
    for i, team in enumerate(teams, 1):
        path = os.path.join(raw_dir, f"bbref_roster_{team}_{args.year}.html")
        if os.path.exists(path) and not args.force:
            page, src = open(path, encoding="utf-8").read(), "cache"
        else:
            if net:
                time.sleep(CRAWL_DELAY)
            try:
                page = fetch(BASE.format(team=team, year=args.year))
            except Exception as e:
                print(f"[{i:2d}/{len(teams)}] {team} !! {str(e)[:60]}")
                failures.append({"team": team, "error": str(e)[:120]})
                continue
            net += 1
            open(path, "w", encoding="utf-8").write(page)
            src = "network"
        try:
            r = parse_roster(page, team, args.year)
        except ValueError as e:
            print(f"[{i:2d}/{len(teams)}] {team} !! {e}")
            failures.append({"team": team, "error": str(e)})
            continue
        rows += r
        known = sum(1 for x in r if x["years_experience"] is not None)
        print(f"[{i:2d}/{len(teams)}] {team} ({src:7s}) {len(r):2d} players, {known:2d} with exp")

    cols = [
        "team",
        "season",
        "bbref_id",
        "player_name",
        "years_experience",
        "birth_date",
        "position",
        "height",
        "weight",
        "college",
    ]
    with open(
        os.path.join(args.out, "roster_experience.csv"), "w", newline="", encoding="utf-8"
    ) as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    json.dump(
        {
            "scraped_at": datetime.now(UTC).isoformat(),
            "source": "basketball-reference.com/teams/",
            "season": f"{args.year - 1}-{str(args.year)[2:]}",
            "convention": (
                "years_experience = seasons COMPLETED BEFORE this season; "
                "rookies are 0. Adjust before using for a later season."
            ),
            "teams_ok": len(teams) - len(failures),
            "failures": failures,
            "rows": len(rows),
        },
        open(os.path.join(args.out, "roster_manifest.json"), "w"),
        indent=2,
    )

    print(f"\n  roster_experience.csv  {len(rows)} players")
    if failures:
        print(f"  FAILURES: {[f['team'] for f in failures]}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
