#!/usr/bin/env python3
"""
Fanspo cap-sheet scraper.

Pulls the embedded __NEXT_DATA__ Apollo cache from each team's cap-sheet page
and normalizes it into one CSV per GraphQL type, plus a combined JSON dump.

The URL slug is decorative -- only the trailing integer selects the team
(/nba/cap-sheets/anything/2 returns the Celtics), so we iterate ids 1..30.

Stdlib only: no pip install required.

Usage:
    python3 fanspo_scrape.py                  # all 30 teams -> ./out
    python3 fanspo_scrape.py --teams 1,2,3    # subset
    python3 fanspo_scrape.py --force          # ignore the raw HTML cache
    python3 fanspo_scrape.py --delay 2.5      # be gentler
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

BASE_URL = "https://fanspo.com/nba/cap-sheets/team/{team_id}"
TEAM_IDS = list(range(1, 31))

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)

# Apollo bookkeeping entries we never want as rows.
SKIP_TYPENAMES = {"Query"}


# --------------------------------------------------------------------------
# fetch
# --------------------------------------------------------------------------


def fetch(url: str, timeout: int = 30, retries: int = 3) -> str:
    """GET a URL with retries and exponential backoff. Returns decoded text."""
    last_err = None
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
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
                return raw.decode("utf-8", errors="replace")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last_err = e
            if attempt < retries - 1:
                backoff = (2**attempt) + random.uniform(0, 0.6)
                print(f"    retry {attempt + 1}/{retries - 1} in {backoff:.1f}s ({e})")
                time.sleep(backoff)
    raise RuntimeError(f"failed after {retries} attempts: {url} ({last_err})")


def extract_apollo_state(html: str) -> dict:
    """Pull props.pageProps.apolloState out of the __NEXT_DATA__ script tag."""
    m = NEXT_DATA_RE.search(html)
    if not m:
        raise ValueError("__NEXT_DATA__ script tag not found -- page structure changed")
    data = json.loads(m.group(1))
    state = data.get("props", {}).get("pageProps", {}).get("apolloState")
    if state is None:
        raise ValueError("props.pageProps.apolloState missing -- page structure changed")
    return state


# --------------------------------------------------------------------------
# normalize
# --------------------------------------------------------------------------


def _deref(value):
    """Apollo stores links as {"__ref": "Type:id"}. Keep just the id."""
    ref = value.get("__ref", "")
    return ref.split(":", 1)[1] if ":" in ref else ref


def flatten(obj: dict, prefix: str = "") -> dict:
    """
    Flatten one Apollo object into a single CSV row.

    - {"__ref": "Type:id"}        -> the bare id
    - [refs, ...]                 -> pipe-joined ids
    - nested inline dict          -> prefixed columns (player_fullName, ...)
    - list of scalars             -> pipe-joined
    """
    row: dict = {}
    for key, value in obj.items():
        if key == "__typename":
            continue
        col = f"{prefix}{key}"

        if isinstance(value, dict):
            if "__ref" in value:
                row[col] = _deref(value)
            else:
                row.update(flatten(value, prefix=f"{col}_"))
        elif isinstance(value, list):
            if value and all(isinstance(v, dict) and "__ref" in v for v in value):
                row[col] = "|".join(_deref(v) for v in value)
            else:
                row[col] = "|".join("" if v is None else str(v) for v in value)
        else:
            row[col] = value
    return row


def collect(state: dict, team_id: int, store: dict) -> dict:
    """
    Fold one page's Apollo state into `store`, keyed by typename then object key.

    Pages carry league-wide objects (all 30 team profiles, shared cap figures),
    so the same object shows up on many pages. We dedupe by Apollo key and
    record every source page in _source_team_ids.
    """
    counts: dict = {}
    for apollo_key, obj in state.items():
        if not isinstance(obj, dict):
            continue
        typename = obj.get("__typename")
        if not typename or typename in SKIP_TYPENAMES:
            continue

        bucket = store.setdefault(typename, {})
        if apollo_key in bucket:
            bucket[apollo_key]["_source_team_ids"].add(team_id)
        else:
            row = flatten(obj)
            row["_source_team_ids"] = {team_id}
            bucket[apollo_key] = row
        counts[typename] = counts.get(typename, 0) + 1
    return counts


# --------------------------------------------------------------------------
# write
# --------------------------------------------------------------------------


def write_csv(path: str, rows: list) -> None:
    """Write rows with the union of all keys as the header, id-first."""
    if not rows:
        return
    keys: list = []
    seen = set()
    for row in rows:
        for k in row:
            if k not in seen:
                seen.add(k)
                keys.append(k)

    def sort_key(k):
        if k == "id":
            return (0, "")
        if k.startswith("_"):
            return (2, k)
        return (1, k)

    keys.sort(key=sort_key)

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def main() -> int:
    ap = argparse.ArgumentParser(description="Scrape Fanspo NBA cap sheets.")
    ap.add_argument(
        "--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
    )
    ap.add_argument("--teams", default="", help="comma-separated team ids (default: 1-30)")
    ap.add_argument("--delay", type=float, default=1.5, help="seconds between requests")
    ap.add_argument("--force", action="store_true", help="refetch even if cached")
    args = ap.parse_args()

    team_ids = [int(t) for t in args.teams.split(",") if t.strip()] if args.teams else TEAM_IDS

    raw_dir = os.path.join(args.out, "raw")
    os.makedirs(raw_dir, exist_ok=True)

    store: dict = {}
    manifest = {
        "scraped_at": datetime.now(UTC).isoformat(),
        "source": "fanspo.com",
        "url_pattern": BASE_URL,
        "note": (
            "Initial HTML payload carries the CURRENT season only. Multi-year salary "
            "grids, per-year option flags, and guarantee status load client-side and "
            "are NOT captured here."
        ),
        "pages": [],
    }

    print(f"Scraping {len(team_ids)} teams -> {args.out}\n")

    for i, team_id in enumerate(team_ids, 1):
        url = BASE_URL.format(team_id=team_id)
        cache_path = os.path.join(raw_dir, f"team_{team_id:02d}.html")

        if os.path.exists(cache_path) and not args.force:
            html = open(cache_path, encoding="utf-8").read()
            source = "cache"
        else:
            print(f"[{i:2d}/{len(team_ids)}] fetching team {team_id} ...")
            html = fetch(url)
            with open(cache_path, "w", encoding="utf-8") as f:
                f.write(html)
            source = "network"
            if i < len(team_ids):
                time.sleep(args.delay + random.uniform(0, 0.4))

        try:
            state = extract_apollo_state(html)
        except ValueError as e:
            print(f"    !! team {team_id}: {e}")
            manifest["pages"].append(
                {"team_id": team_id, "url": url, "status": "parse_failed", "error": str(e)}
            )
            continue

        counts = collect(state, team_id, store)

        title = re.search(r"<title>([^<]*)</title>", html)
        team_name = title.group(1).split(" 20")[0].strip() if title else f"team {team_id}"

        manifest["pages"].append(
            {
                "team_id": team_id,
                "team_name": team_name,
                "url": url,
                "status": "ok",
                "source": source,
                "sha256": hashlib.sha256(html.encode()).hexdigest()[:16],
                "objects": counts,
            }
        )
        print(
            f"[{i:2d}/{len(team_ids)}] {team_name:24s} ({source}) {sum(counts.values()):4d} objects"
        )

    # ---- emit ----
    print("\nWriting output ...")
    combined: dict = {}
    for typename, bucket in sorted(store.items()):
        rows = []
        for row in bucket.values():
            row = dict(row)
            row["_source_team_ids"] = "|".join(str(t) for t in sorted(row["_source_team_ids"]))
            rows.append(row)

        stem = typename.replace("nba_", "")
        # split camelCase but keep acronyms intact: PlayerLEBRON -> player_lebron
        stem = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", stem).lower()
        write_csv(os.path.join(args.out, f"{stem}.csv"), rows)
        combined[typename] = rows
        print(f"  {stem + '.csv':32s} {len(rows):5d} rows")

    with open(os.path.join(args.out, "all.json"), "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2, ensure_ascii=False)

    manifest["totals"] = {t: len(r) for t, r in combined.items()}
    with open(os.path.join(args.out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    ok = sum(1 for p in manifest["pages"] if p["status"] == "ok")
    print(f"\nDone. {ok}/{len(team_ids)} pages parsed.")
    return 0 if ok == len(team_ids) else 1


if __name__ == "__main__":
    sys.exit(main())
