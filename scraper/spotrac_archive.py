#!/usr/bin/env python3
"""
Spotrac cap-sheet scraper, via the Wayback Machine.

Spotrac carries four fields no other source we found does: guarantee DATES,
partial guarantee amounts, trade kickers, and likely/unlikely incentives.
Spotrac blocks the archiver from mid-2026 onward, so we read archived
snapshots rather than the live site.

Complements bbref_contracts.py -- that one has multi-year salaries, per-year
options and signing dates; this one has the fields it lacks. Neither is a
superset of the other.

The high-value output is spotrac_decisions.csv: a dated calendar of option and
guarantee decisions, e.g.

    6/29/2026   Trae Young      PLAYER 2026-27 Player Option
    1/10/2027   Mouhamed Gueye  GUARANTEED 2026-27 Guaranteed     $2,406,205

IMPORTANT: every team's data is as-of a DIFFERENT snapshot date, because
archive coverage is uneven. snapshot_date is on every row and in the manifest.
Do not treat this as one coherent league state.

Stdlib only.

Usage:
    python3 spotrac_archive.py                    # year 2026, all teams
    python3 spotrac_archive.py --year 2024        # historical
    python3 spotrac_archive.py --teams atlanta-hawks
    python3 spotrac_archive.py --refresh-cdx      # re-query the archive index
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
import urllib.parse
import urllib.request
from datetime import UTC, datetime

CDX = (
    "http://web.archive.org/cdx/search/cdx?url={target}"
    "&output=json&fl=original,timestamp,statuscode&limit=800&collapse=digest"
)
WAYBACK = "https://web.archive.org/web/{ts}id_/{url}"

# Spotrac has used more than one slug and more than one path for some teams.
TEAMS = {
    "atlanta-hawks": [],
    "boston-celtics": [],
    "brooklyn-nets": [],
    "charlotte-hornets": [],
    "chicago-bulls": [],
    "cleveland-cavaliers": [],
    "dallas-mavericks": [],
    "denver-nuggets": [],
    "detroit-pistons": [],
    "golden-state-warriors": [],
    "houston-rockets": [],
    "indiana-pacers": [],
    "los-angeles-clippers": ["la-clippers"],
    "los-angeles-lakers": [],
    "memphis-grizzlies": [],
    "miami-heat": [],
    "milwaukee-bucks": [],
    "minnesota-timberwolves": [],
    "new-orleans-pelicans": [],
    "new-york-knicks": [],
    "oklahoma-city-thunder": [],
    "orlando-magic": [],
    "philadelphia-76ers": [],
    "phoenix-suns": [],
    "portland-trail-blazers": [],
    "sacramento-kings": [],
    "san-antonio-spurs": [],
    "toronto-raptors": [],
    "utah-jazz": [],
    "washington-wizards": [],
}

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

TAG_RE = re.compile(r"<[^>]+>")
TABLE_RE = re.compile(r"<table.*?</table>", re.DOTALL)
ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL)
TH_RE = re.compile(r"<th[^>]*>(.*?)</th>", re.DOTALL)
TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL)
ANCHOR_RE = re.compile(r"<a[^>]*>(.*?)</a>", re.DOTALL)
SEASON_RE = re.compile(r"(\d{4}-\d{2})")


def txt(fragment: str) -> str:
    return re.sub(r"\s+", " ", html_mod.unescape(TAG_RE.sub(" ", fragment))).strip()


def player_name(cell_html: str) -> str:
    """
    Spotrac prefixes the display name with a sort-key surname, so the raw cell
    reads "Johnson Jalen Johnson". Prefer the anchor text; else drop a leading
    duplicated surname.
    """
    a = ANCHOR_RE.search(cell_html)
    if a:
        name = txt(a.group(1))
        if name:
            return name
    raw = txt(cell_html)
    parts = raw.split()
    if len(parts) >= 3 and parts[0] == parts[-1]:
        return " ".join(parts[1:])
    return raw


def money(s: str):
    if not s:
        return None
    neg = s.strip().startswith("-") and any(ch.isdigit() for ch in s)
    d = re.sub(r"[^\d]", "", s)
    if not d:
        return None
    return -int(d) if neg else int(d)


def fetch(url: str, retries: int = 3, timeout: int = 60) -> str:
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
        except Exception as e:
            last = e
            if attempt < retries - 1:
                time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"fetch failed: {url} ({last})")


# --------------------------------------------------------------------------
# snapshot discovery
# --------------------------------------------------------------------------


def cdx_lookup(slug: str) -> list:
    try:
        body = fetch(CDX.format(target=urllib.parse.quote(f"spotrac.com/nba/{slug}/cap*")))
        rows = json.loads(body or "[]")
        return [r for r in rows[1:] if len(r) >= 3 and r[2] == "200"]
    except Exception as e:
        print(f"      cdx error for {slug}: {str(e)[:60]}")
        return []


def pick_snapshot(candidates: list, year: int):
    """
    Prefer the explicit /cap/_/year/{year} form, then a plain /cap/ page, then
    /cap-hit/. Within a form, take the snapshot closest to that season.
    """

    def rank(row):
        url = row[0]
        # Spotrac has used two year-bearing forms over time:
        #   /cap/_/year/2026   (current)
        #   /cap/2026/         (older -- Chicago only has this one)
        if f"/year/{year}" in url or re.search(rf"/cap/{year}/?$", url):
            return 0
        if re.search(r"/cap/?$", url) or re.search(r"/cap/?\?", url):
            return 1
        if "/cap-hit" in url:
            return 2
        # a different year, either form -- last resort, but better than nothing
        if "/year/" in url or re.search(r"/cap/\d{4}/?$", url):
            return 4
        return 3

    scored = [(rank(r), r) for r in candidates]
    usable = [s for s in scored if s[0] < 4]
    if not usable:
        # nothing on target: take the nearest available year rather than nothing
        alt = [s for s in scored if s[0] == 4]
        if not alt:
            return None

        def year_of(row):
            m = re.search(r"/(?:year/)?(\d{4})/?$", row[0])
            return int(m.group(1)) if m else 9999

        alt.sort(key=lambda s: (abs(year_of(s[1]) - year), s[1][1]))
        return alt[0][1]
    scored = usable
    best = min(s[0] for s in scored)
    pool = [r for s, r in scored if s == best]
    # snapshot taken during the target league year is most representative
    target = f"{year}"
    pool.sort(key=lambda r: (0 if r[1].startswith(target) else 1, r[1]), reverse=False)
    return pool[-1] if pool[0][1].startswith(target) is False else pool[0]


# --------------------------------------------------------------------------
# table parsing -- identified by header signature, not position
# --------------------------------------------------------------------------


def tables_with_headers(page_html: str) -> list:
    out = []
    for t in TABLE_RE.findall(page_html):
        headers = [txt(x) for x in TH_RE.findall(t)]
        headers = [h for h in headers if h]
        rows = [r for r in ROW_RE.findall(t) if "<td" in r]
        if headers and rows:
            out.append((headers, rows, t))
    return out


def has(headers: list, *needles) -> bool:
    joined = " | ".join(headers).lower()
    return all(n.lower() in joined for n in needles)


def parse_decisions(rows: list, team: str, snap: str) -> list:
    """Deadline Date | Player | Type | Value -- options, guarantees, QOs."""
    out = []
    for r in rows:
        c = TD_RE.findall(r)
        if len(c) < 3:
            continue
        date_s, player_s, type_s = txt(c[0]), player_name(c[1]), txt(c[2])
        value_s = txt(c[3]) if len(c) > 3 else ""
        if not type_s:
            continue
        season = SEASON_RE.search(type_s)
        head = type_s.split()[0].upper() if type_s.split() else ""
        low = type_s.lower()
        if "option" in low:
            kind = "option"
            holder = (
                "player" if "player option" in low else ("club" if "club option" in low else None)
            )
        elif "qualifying offer" in low:
            kind, holder = "qualifying_offer", None
        elif "guaranteed" in low or head == "GUARANTEED":
            kind, holder = "guarantee", None
        elif "extension eligible" in low:
            # extension eligibility windows -- feeds task 7.4
            kind, holder = "extension_eligible", None
        else:
            kind, holder = "other", None
        note = None
        if "—" in type_s:
            note = type_s.split("—", 1)[1].strip()
        elif " - " in type_s:
            note = type_s.split(" - ", 1)[1].strip()
        out.append(
            {
                "team": team,
                "snapshot_date": snap,
                "deadline_date": date_s or None,
                "player_name": player_s,
                "kind": kind,
                "holder": holder,
                "season": season.group(1) if season else None,
                "value": money(value_s),
                "note": note,
                "raw_type": type_s,
            }
        )
    return out


def parse_roster(rows: list, headers: list, team: str, snap: str) -> list:
    idx = {h.lower(): i for i, h in enumerate(headers)}

    def col(*names):
        for n in names:
            for k, i in idx.items():
                if k.startswith(n):
                    return i
        return None

    i_pos, i_age = col("pos"), col("age")
    i_type, i_cap = col("type"), col("cap hit")
    i_base, i_lik = col("base salary"), col("incentives likely")
    i_unl, i_tb = col("incentives unlikely"), col("trade bonus")
    i_gtd = col("guaranteed")
    out = []
    for r in rows:
        c = TD_RE.findall(r)
        if len(c) < 3:
            continue
        g = lambda i: txt(c[i]) if i is not None and i < len(c) else ""  # noqa: E731
        out.append(
            {
                "team": team,
                "snapshot_date": snap,
                "player_name": player_name(c[0]),
                "position": g(i_pos) or None,
                "age": g(i_age) or None,
                # source renders sign-and-trade as "S&T;" -- a stray entity semicolon
                "contract_type": re.sub(r"&(\w);", r"&\1", g(i_type)).rstrip(";") or None,
                "cap_hit": money(g(i_cap)),
                "base_salary": money(g(i_base)),
                "incentives_likely": money(g(i_lik)),
                "incentives_unlikely": money(g(i_unl)),
                "trade_bonus_proration": money(g(i_tb)),
                "guaranteed": money(g(i_gtd)),
            }
        )
    return out


def parse_exceptions(rows: list, team: str, snap: str) -> list:
    out = []
    for r in rows:
        c = [txt(x) for x in TD_RE.findall(r)]
        if len(c) < 5:
            continue
        out.append(
            {
                "team": team,
                "snapshot_date": snap,
                "exception_type": c[0] or None,
                "reason": c[1] or None,
                "used_on": c[2] or None,
                "expires": c[3] or None,
                "original": money(c[4]),
                "available": money(c[5]) if len(c) > 5 else None,
            }
        )
    return out


def parse_holds(rows: list, team: str, snap: str) -> list:
    out = []
    for r in rows:
        c = TD_RE.findall(r)
        if len(c) < 4:
            continue
        cells = [txt(x) for x in c]
        rights = next(
            (v for v in cells if v in ("Bird", "Early Bird", "Non-Bird", "Non Bird")), None
        )
        out.append(
            {
                "team": team,
                "snapshot_date": snap,
                "player_name": player_name(c[0]),
                "position": cells[1] or None,
                "age": cells[2] or None,
                "contract_type": cells[3] or None,
                "cap_hit": money(cells[4]) if len(cells) > 4 else None,
                "qualifying_offer": money(cells[6]) if len(cells) > 6 else None,
                "bird_rights": rights,
            }
        )
    return out


def write_csv(path, rows, cols):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="Scrape archived Spotrac NBA cap sheets.")
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--out", default=os.path.join(here, "out"))
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--teams", default="")
    ap.add_argument("--refresh-cdx", action="store_true")
    ap.add_argument("--delay", type=float, default=1.0)
    args = ap.parse_args()

    slugs = [s.strip() for s in args.teams.split(",") if s.strip()] or list(TEAMS.keys())
    raw_dir = os.path.join(args.out, "raw")
    os.makedirs(raw_dir, exist_ok=True)
    cdx_cache_path = os.path.join(raw_dir, "spotrac_cdx.json")
    cdx_cache = {}
    if os.path.exists(cdx_cache_path) and not args.refresh_cdx:
        cdx_cache = json.load(open(cdx_cache_path))

    roster, holds, exceptions, decisions, pages = [], [], [], [], []

    for i, slug in enumerate(slugs, 1):
        tried = [slug] + TEAMS.get(slug, [])
        cands = []
        for s in tried:
            # An empty result is usually a failed/timed-out archive query, not a
            # genuine absence -- never cache it, or the team is lost forever.
            if not cdx_cache.get(s):
                found = cdx_lookup(s)
                if found:
                    cdx_cache[s] = found
                    json.dump(cdx_cache, open(cdx_cache_path, "w"))
                else:
                    print(f"      no cdx results for {s} (not cached; will retry next run)")
                time.sleep(args.delay)
            cands += cdx_cache.get(s, [])

        chosen = pick_snapshot(cands, args.year)
        if not chosen:
            print(f"[{i:2d}/{len(slugs)}] {slug:24s} no usable snapshot")
            pages.append({"team": slug, "status": "no_snapshot"})
            continue

        url, ts = chosen[0], chosen[1]
        snap = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
        cache_path = os.path.join(raw_dir, f"spotrac_{slug}_{args.year}.html")
        if os.path.exists(cache_path):
            page = open(cache_path, encoding="utf-8").read()
            src = "cache"
        else:
            try:
                page = fetch(WAYBACK.format(ts=ts, url=url))
            except Exception as e:
                print(f"[{i:2d}/{len(slugs)}] {slug:24s} fetch failed: {str(e)[:50]}")
                pages.append({"team": slug, "status": "fetch_failed", "url": url})
                continue
            open(cache_path, "w", encoding="utf-8").write(page)
            src = "network"
            time.sleep(args.delay)

        counts = {"roster": 0, "holds": 0, "tpe": 0, "decisions": 0}
        for headers, rows, _t in tables_with_headers(page):
            if has(headers, "deadline date", "player"):
                d = parse_decisions(rows, slug, snap)
                decisions += d
                counts["decisions"] += len(d)
            elif has(headers, "cap hit", "guaranteed"):
                d = parse_roster(rows, headers, slug, snap)
                roster += d
                counts["roster"] += len(d)
            elif has(headers, "qualifying offer"):
                d = parse_holds(rows, slug, snap)
                holds += d
                counts["holds"] += len(d)
            elif has(headers, "expires", "available"):
                d = parse_exceptions(rows, slug, snap)
                exceptions += d
                counts["tpe"] += len(d)

        print(
            f"[{i:2d}/{len(slugs)}] {slug:24s} {snap} ({src:7s}) "
            f"roster={counts['roster']:2d} holds={counts['holds']:2d} "
            f"tpe={counts['tpe']:2d} decisions={counts['decisions']:2d}"
        )
        pages.append(
            {
                "team": slug,
                "status": "ok",
                "snapshot_date": snap,
                "url": url,
                "source": src,
                **counts,
            }
        )

    os.makedirs(args.out, exist_ok=True)
    write_csv(
        os.path.join(args.out, "spotrac_decisions.csv"),
        decisions,
        [
            "team",
            "snapshot_date",
            "deadline_date",
            "player_name",
            "kind",
            "holder",
            "season",
            "value",
            "note",
            "raw_type",
        ],
    )
    write_csv(
        os.path.join(args.out, "spotrac_roster.csv"),
        roster,
        [
            "team",
            "snapshot_date",
            "player_name",
            "position",
            "age",
            "contract_type",
            "cap_hit",
            "base_salary",
            "incentives_likely",
            "incentives_unlikely",
            "trade_bonus_proration",
            "guaranteed",
        ],
    )
    write_csv(
        os.path.join(args.out, "spotrac_cap_holds.csv"),
        holds,
        [
            "team",
            "snapshot_date",
            "player_name",
            "position",
            "age",
            "contract_type",
            "cap_hit",
            "qualifying_offer",
            "bird_rights",
        ],
    )
    write_csv(
        os.path.join(args.out, "spotrac_trade_exceptions.csv"),
        exceptions,
        [
            "team",
            "snapshot_date",
            "exception_type",
            "reason",
            "used_on",
            "expires",
            "original",
            "available",
        ],
    )

    ok = [p for p in pages if p.get("status") == "ok"]
    manifest = {
        "scraped_at": datetime.now(UTC).isoformat(),
        "source": "web.archive.org snapshots of spotrac.com",
        "target_year": args.year,
        "teams_ok": len(ok),
        "teams_requested": len(slugs),
        "snapshot_dates": sorted({p["snapshot_date"] for p in ok}),
        "warning": (
            "Each team's rows are as-of that team's own snapshot_date. "
            "Archive coverage is uneven; this is NOT one coherent league state."
        ),
        "pages": pages,
        "rows": {
            "decisions": len(decisions),
            "roster": len(roster),
            "cap_holds": len(holds),
            "trade_exceptions": len(exceptions),
        },
    }
    json.dump(manifest, open(os.path.join(args.out, "spotrac_manifest.json"), "w"), indent=2)

    print(f"\n  spotrac_decisions.csv        {len(decisions):5d}")
    print(f"  spotrac_roster.csv           {len(roster):5d}")
    print(f"  spotrac_cap_holds.csv        {len(holds):5d}")
    print(f"  spotrac_trade_exceptions.csv {len(exceptions):5d}")
    print(f"  teams with data: {len(ok)}/{len(slugs)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
