#!/usr/bin/env python3
"""
Basketball-Reference awards scraper.

Collects the three awards that make up the CBA's "Higher Max Criteria"
(Article II, Section 7, pp. 60-61): All-NBA team selections, Defensive Player
of the Year, and MVP. Those three -- and only those three -- gate the 30% and
35% maximum salary tiers and the rookie-scale extension escalators.

All-Star selections are deliberately NOT collected. They are not part of the
Higher Max Criteria; they belong to a separate defined term ("Generally
Recognized League Honors", Article I(cc)) that governs incentive compensation.
See division-of-labor.md section 4.2.

Output is tidy long format -- one row per (player, season, award) -- which is
what the extension-eligibility check in task 7.4 wants to query.

Player ids are Basketball-Reference ids (e.g. jokicni01), which join directly
to the trailing id column in data/player_yearly_salary.csv.

Respects the site's robots.txt crawl-delay of 3 seconds. /awards/ is not
disallowed. Stdlib only.

Usage:
    python3 bbref_awards.py                      # 2020-21 forward -> ./out
    python3 bbref_awards.py --from-season 2019   # more history
    python3 bbref_awards.py --force              # ignore the raw HTML cache
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

BASE = "https://www.basketball-reference.com/awards/{page}.html"
CRAWL_DELAY = 3.0  # robots.txt: Crawl-delay: 3

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL)
CELL_RE = re.compile(r"<(t[hd])[^>]*data-stat=\"([^\"]+)\"[^>]*>(.*?)</\1>", re.DOTALL)
PLAYER_ID_RE = re.compile(r"/players/\w/(\w+)\.html")
TAG_RE = re.compile(r"<[^>]+>")


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
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last = e
            if attempt < retries - 1:
                wait = CRAWL_DELAY * (attempt + 2)
                print(f"    retry {attempt + 1} in {wait:.0f}s ({e})")
                time.sleep(wait)
    raise RuntimeError(f"failed: {url} ({last})")


def text(fragment: str) -> str:
    return html_mod.unescape(TAG_RE.sub("", fragment)).strip()


def table_rows(page_html: str, table_id: str):
    """Yield {data-stat: (text, raw_html)} dicts for each row of a table."""
    m = re.search(rf'<table[^>]*id="{re.escape(table_id)}".*?</table>', page_html, re.DOTALL)
    if not m:
        raise ValueError(f"table {table_id} not found")
    for row in ROW_RE.findall(m.group(0)):
        cells = {stat: (text(inner), inner) for _tag, stat, inner in CELL_RE.findall(row)}
        if cells:
            yield cells


def season_start(season: str) -> int:
    """'2023-24' -> 2023"""
    return int(season.split("-")[0])


def season_id(season: str) -> str:
    """'2023-24' -> '2023-2024' (the form Fanspo uses)"""
    start = season_start(season)
    return f"{start}-{start + 1}"


def parse_all_nba(page_html: str, since: int) -> list:
    out = []
    for cells in table_rows(page_html, "awards_all_league"):
        season = cells.get("season", ("", ""))[0]
        if not re.match(r"^\d{4}-\d{2}$", season) or season_start(season) < since:
            continue
        if cells.get("lg_id", ("",))[0] != "NBA":
            continue
        tier = cells.get("all_team", ("", ""))[0]  # '1st' / '2nd' / '3rd'
        # the five player slots are columns data-stat="1".."5"
        for stat, (txt, raw) in cells.items():
            if not stat.isdigit():
                continue
            pid = PLAYER_ID_RE.search(raw)
            if not pid:
                continue
            name = re.sub(r"\s+[CFG]$", "", txt).strip()
            pos = txt[len(name) :].strip() or None
            out.append(
                {
                    "season": season,
                    "season_id": season_id(season),
                    "award": "All-NBA",
                    "tier": tier,
                    "player_name": name,
                    "bbref_id": pid.group(1),
                    "position": pos,
                }
            )
    return out


def parse_single_winner(page_html: str, table_id: str, award: str, since: int) -> list:
    out = []
    for cells in table_rows(page_html, table_id):
        season = cells.get("season", ("", ""))[0]
        if not re.match(r"^\d{4}-\d{2}$", season) or season_start(season) < since:
            continue
        player = cells.get("player")
        if not player:
            continue
        pid = PLAYER_ID_RE.search(player[1])
        if not pid:
            continue
        out.append(
            {
                "season": season,
                "season_id": season_id(season),
                "award": award,
                "tier": "Winner",
                "player_name": player[0],
                "bbref_id": pid.group(1),
                "position": None,
            }
        )
    return out


def main() -> int:
    # 2020 is the floor, not 2023: Higher Max Criteria looks back three seasons,
    # so adjudicating a 2023-24 decision needs 2020-21 awards.
    ap = argparse.ArgumentParser(description="Scrape NBA awards from Basketball-Reference.")
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--out", default=os.path.join(here, "out"))
    ap.add_argument(
        "--from-season",
        type=int,
        default=2020,
        help="earliest season START year (default 2020 = the 2020-21 season)",
    )
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    raw_dir = os.path.join(args.out, "raw")
    os.makedirs(raw_dir, exist_ok=True)

    pages = {"all_league": "All-NBA", "dpoy": "Defensive Player of the Year", "mvp": "MVP"}
    fetched, rows = {}, []

    for i, page in enumerate(pages):
        path = os.path.join(raw_dir, f"bbref_{page}.html")
        if os.path.exists(path) and not args.force:
            fetched[page] = open(path, encoding="utf-8").read()
            print(f"  {page:12s} (cache)")
        else:
            if i:
                time.sleep(CRAWL_DELAY)
            print(f"  {page:12s} fetching ...")
            fetched[page] = fetch(BASE.format(page=page))
            with open(path, "w", encoding="utf-8") as f:
                f.write(fetched[page])

    rows += parse_all_nba(fetched["all_league"], args.from_season)
    rows += parse_single_winner(fetched["dpoy"], "dpoy_NBA", "DPOY", args.from_season)
    rows += parse_single_winner(fetched["mvp"], "mvp_NBA", "MVP", args.from_season)

    rows.sort(key=lambda r: (r["season"], r["award"], r["tier"], r["player_name"]))

    os.makedirs(args.out, exist_ok=True)
    out_csv = os.path.join(args.out, "awards.csv")
    cols = ["season", "season_id", "award", "tier", "player_name", "bbref_id", "position"]
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    manifest = {
        "scraped_at": datetime.now(UTC).isoformat(),
        "source": "basketball-reference.com/awards/",
        "crawl_delay_s": CRAWL_DELAY,
        "from_season": args.from_season,
        "awards_collected": ["All-NBA (1st/2nd/3rd)", "DPOY", "MVP"],
        "deliberately_excluded": [
            "All-Star -- not part of Higher Max Criteria (CBA Art. II sec. 7)"
        ],
        "cba_basis": "Higher Max Criteria, Article II, Section 7, pp. 60-61",
        "row_count": len(rows),
    }
    with open(os.path.join(args.out, "awards_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    seasons = sorted({r["season"] for r in rows})
    print(f"\n  awards.csv  {len(rows)} rows, seasons {seasons[0]}..{seasons[-1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
