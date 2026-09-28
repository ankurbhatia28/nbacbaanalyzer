#!/usr/bin/env python3
"""
SalarySwish scraper: hard-cap ceilings and trade detail.

Two things no other source we have provides:

1. **Hard-cap ceilings with their triggering transaction.** The CBA never uses
   the phrase "hard cap" -- the mechanism is Article VII Sec. 2(e)(2)(i)(B): a
   team that engages in a transaction listed in the Transaction Restrictions
   Table (Sec. 2(e)(4), rows A-K) may not exceed that row's "Applicable Apron
   Level" for the rest of the Salary Cap Year. This site's two tables map
   almost column-for-column onto rows A-G (first apron) and H-K (second).

2. **Cash in trades, with direction.** division-of-labor.md Sec. 4.1 wrote cash
   considerations off as unobtainable. That was wrong -- this source has both
   the amount and which team paid.

A team can hold more than one ceiling; the lowest binds. Atlanta appears in both
tables (first-apron TP-MLE, second-apron cash) and is "Capped At: 1st Apron".
Model ceilings as a set and take the minimum -- never a single field.

Stdlib only. robots.txt disallows only /maintenance.

Usage:
    python3 salaryswish_scrape.py                      # hard caps only
    python3 salaryswish_scrape.py --what all --to-id 520 --from-id 480
    python3 salaryswish_scrape.py --what trades --from-id 1 --to-id 520
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

BASE = "https://www.salaryswish.com"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

TAG_RE = re.compile(r"<[^>]+>")
TABLE_RE = re.compile(r"<table.*?</table>", re.DOTALL)
TR_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL)
TH_RE = re.compile(r"<th[^>]*>(.*?)</th>", re.DOTALL)
TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL)
ISO_DATE_RE = re.compile(r"(20\d\d-\d\d-\d\d)")
TEAM_SLUG_RE = re.compile(r'href="/teams/([a-z0-9-]+)"')
ACQUIRE_RE = re.compile(r"^(.*?)\s+Acquire:")
CASH_RE = re.compile(r"\$([\d,]+)\s*(?:in\s+)?cash", re.I)
TPE_RE = re.compile(r"Trade Exceptions Generated:\s*(.*?)(?:Cap Hit Sum|$)", re.S)


def txt(s: str) -> str:
    return re.sub(r"\s+", " ", html_mod.unescape(TAG_RE.sub(" ", s))).strip()


def money(s: str):
    d = re.sub(r"[^\d]", "", s or "")
    return int(d) if d else None


def fetch(url: str, retries: int = 3, timeout: int = 30) -> str:
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
            with urllib.request.urlopen(req, timeout=timeout) as r:
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
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"fetch failed: {url} ({last})")


def cached(path: str, url: str, force: bool, delay: float):
    if os.path.exists(path) and not force:
        return open(path, encoding="utf-8").read(), "cache"
    page = fetch(url)
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    time.sleep(delay)
    return page, "network"


# --------------------------------------------------------------------------
# hard caps
# --------------------------------------------------------------------------


def parse_hard_caps(page: str) -> list:
    """
    Two tables. Table 0's columns are first-apron triggers (Transaction
    Restrictions Table rows A-G); table 1's are second-apron triggers (H-K).
    A cell is non-empty only when that trigger fired for that team.
    """
    out = []
    for ti, table in enumerate(TABLE_RE.findall(page)):
        headers = [h for h in (txt(x) for x in TH_RE.findall(table)) if h]
        if not headers or headers[0].lower() != "team":
            continue
        apron_scope = "first" if ti == 0 else "second"
        for row in (r for r in TR_RE.findall(table) if "<td" in r):
            cells = [txt(c) for c in TD_RE.findall(row)]
            if not cells:
                continue
            slug = TEAM_SLUG_RE.search(row)
            team = cells[0]
            capped_at = cells[1] if len(cells) > 1 else None
            # columns 2..n are the trigger categories in header order
            for i, col in enumerate(headers[2:], start=2):
                val = cells[i] if i < len(cells) else ""
                if not val:
                    continue
                out.append(
                    {
                        "team": team,
                        "team_slug": slug.group(1) if slug else None,
                        "capped_at": capped_at,
                        "trigger_scope": apron_scope,
                        "trigger_category": col,
                        "trigger_detail": val,
                    }
                )
    return out


# --------------------------------------------------------------------------
# trades
# --------------------------------------------------------------------------


def parse_trade(page: str, trade_id: int) -> list:
    tables = TABLE_RE.findall(page)
    if not tables:
        return []
    body = tables[0]
    iso = ISO_DATE_RE.search(page)
    date = iso.group(1) if iso else None
    label = None
    legs = []
    for row in (r for r in TR_RE.findall(body) if "<td" in r):
        cells = [txt(c) for c in TD_RE.findall(row)]
        for cell in cells:
            if not cell or cell.upper() in ("DATE", "TRADE DETAILS"):
                continue
            if re.fullmatch(r"[A-Za-z-]+(?:\s+[A-Za-z-]+)?\s+Trade", cell):
                label = cell
                continue
            m = ACQUIRE_RE.match(cell)
            if not m:
                continue
            team = m.group(1).strip()
            cash = CASH_RE.search(cell)
            tpe = TPE_RE.search(cell)
            legs.append(
                {
                    "trade_id": trade_id,
                    "date": date,
                    "trade_label": label,
                    "team": team,
                    "cash_received": money(cash.group(1)) if cash else None,
                    "tpes_generated": txt(tpe.group(1))[:300] if tpe else None,
                    "detail": cell,
                }
            )
    return legs


def write_csv(path: str, rows: list, cols: list) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="Scrape SalarySwish hard caps and trades.")
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--out", default=os.path.join(here, "out"))
    ap.add_argument("--what", choices=["hardcaps", "trades", "all"], default="hardcaps")
    ap.add_argument("--from-id", type=int, default=480)
    ap.add_argument("--to-id", type=int, default=520)
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    raw = os.path.join(args.out, "raw")
    os.makedirs(raw, exist_ok=True)
    manifest = {
        "scraped_at": datetime.now(UTC).isoformat(),
        "source": "salaryswish.com",
        "note": (
            "Hard-cap columns map onto the CBA Transaction Restrictions Table "
            "(Art. VII Sec. 2(e)(4), rows A-K). A team may hold several ceilings; "
            "the lowest binds."
        ),
    }

    if args.what in ("hardcaps", "all"):
        page, src = cached(
            os.path.join(raw, "salaryswish_hard_caps.html"),
            f"{BASE}/hard-cap-tracker",
            args.force,
            args.delay,
        )
        caps = parse_hard_caps(page)
        write_csv(
            os.path.join(args.out, "salaryswish_hard_caps.csv"),
            caps,
            [
                "team",
                "team_slug",
                "capped_at",
                "trigger_scope",
                "trigger_category",
                "trigger_detail",
            ],
        )
        teams = {c["team"] for c in caps}
        print(f"  hard caps ({src}): {len(caps)} triggers across {len(teams)} teams")
        manifest["hard_cap_rows"] = len(caps)

    if args.what in ("trades", "all"):
        legs, ok, missing = [], 0, 0
        for tid in range(args.from_id, args.to_id + 1):
            path = os.path.join(raw, f"salaryswish_trade_{tid}.html")
            try:
                page, _ = cached(path, f"{BASE}/trades/{tid}", args.force, args.delay)
            except urllib.error.HTTPError:
                missing += 1
                continue
            except Exception as e:
                print(f"    trade {tid}: {str(e)[:50]}")
                continue
            got = parse_trade(page, tid)
            if got:
                ok += 1
                legs += got
        write_csv(
            os.path.join(args.out, "salaryswish_trade_legs.csv"),
            legs,
            [
                "trade_id",
                "date",
                "trade_label",
                "team",
                "cash_received",
                "tpes_generated",
                "detail",
            ],
        )
        print(f"  trades: {ok} parsed, {missing} missing, {len(legs)} team-legs")
        manifest["trade_legs"] = len(legs)

    with open(os.path.join(args.out, "salaryswish_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
