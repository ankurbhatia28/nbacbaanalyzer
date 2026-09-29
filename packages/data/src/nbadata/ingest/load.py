"""
Ingest: scraper CSVs -> SQLite (task 2.2).

Orchestration only. Identity resolution lives in `resolve`, source ranking in
`precedence`, conflict reporting in `reconcile`. Run it with:

    python -m nbadata.ingest.load --out nbacba.db
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import UTC, datetime
from pathlib import Path

from ..db import build
from .names import normalise
from .overrides import apply_pick_overrides, load_pick_overrides
from .precedence import Src
from .reconcile import Reconciler
from .resolve import ResolutionReport
from .teams import canonical_team, from_display, from_slug

DEFAULT_CSV_DIR = Path(__file__).resolve().parents[5] / "scraper" / "out"
SEASON = "2026-2027"


def rows(directory: Path, name: str) -> list[dict[str, str]]:
    path = directory / name
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _iso_date(value: str | None) -> str | None:
    """Basketball-Reference writes 'August 26, 1989'; normalise so sources compare."""
    if not value:
        return None
    for fmt in ("%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def as_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


@dataclass
class IngestReport:
    counts: dict[str, int] = dc_field(default_factory=dict)
    resolution: dict[str, int] = dc_field(default_factory=dict)
    reconciliation: dict[str, int] = dc_field(default_factory=dict)
    unresolved: list[str] = dc_field(default_factory=list)
    overrides: dict[str, int] = dc_field(default_factory=dict)

    def __getitem__(self, key: str) -> object:  # convenience for tests
        return getattr(self, key)


def load(csv_dir: Path, db_path: Path) -> IngestReport:
    conn = build(db_path)
    ids = ResolutionReport()
    rec = Reconciler()
    counts: dict[str, int] = {}

    # ---- teams ----------------------------------------------------------
    profiles = rows(csv_dir, "team_profile.csv")
    team_rows, fanspo_to_tri = [], {}
    for r in profiles:
        tri: str | None = canonical_team(r.get("triName"))
        if not tri:
            continue
        fanspo_to_tri[r["teamId"]] = tri
        team_rows.append(
            (tri, r.get("longName"), r.get("teamId"), r.get("confName"), r.get("divName"))
        )
    conn.executemany("INSERT OR REPLACE INTO teams VALUES (?,?,?,?,?)", team_rows)
    counts["teams"] = len(team_rows)

    # ---- seasons --------------------------------------------------------
    season_rows = [
        (
            r["seasonId"],
            as_int(r["cap"]),
            as_int(r["tax"]),
            as_int(r["apron"]),
            as_int(r["apronTwo"]),
            as_int(r["nonTaxpayerMLE"]),
            as_int(r["taxpayerMLE"]),
            as_int(r["roomMLE"]),
            as_int(r["biAnnualEx"]),
            Src.FANSPO.value,
        )
        for r in rows(csv_dir, "salary_cap_figure.csv")
        if r.get("cap")
    ]
    conn.executemany("INSERT OR REPLACE INTO seasons VALUES (?,?,?,?,?,?,?,?,?,?)", season_rows)
    counts["seasons"] = len(season_rows)

    # ---- identities (B-R first: it carries stable ids) ------------------
    for r in rows(csv_dir, "roster_experience.csv"):
        ids.observe(r["player_name"], Src.BBREF_ROSTER.value, bbref_id=r["bbref_id"])
    for r in rows(csv_dir, "contract_totals.csv"):
        ids.observe(r["player_name"], Src.BBREF_CONTRACTS.value, bbref_id=r["bbref_id"])
    for r in rows(csv_dir, "player.csv"):
        ids.observe(r["fullName"], Src.FANSPO.value, nba_id=r["id"])
    for r in rows(csv_dir, "spotrac_roster.csv"):
        ids.observe(r["player_name"], Src.SPOTRAC.value)

    yos = {
        r["bbref_id"]: as_int(r["years_experience"]) for r in rows(csv_dir, "roster_experience.csv")
    }

    # birth_date is carried by two sources for the same fact, so it goes through
    # the reconciler: unlike salary (where sources measure different things),
    # any disagreement here is a genuine data problem rather than a definition
    # difference.
    bbref_birth = {
        normalise(r["player_name"]): _iso_date(r["birth_date"])
        for r in rows(csv_dir, "roster_experience.csv")
    }
    # Fanspo splits identity from biography: player.csv carries an `info` ref
    # into player_info.csv, and the denormalised info_birthDate column is empty.
    fanspo_info = {r["id"]: r for r in rows(csv_dir, "player_info.csv")}
    fanspo_birth = {
        normalise(r["fullName"]): (fanspo_info.get(r.get("info", ""), {}).get("birthDate") or "")[
            :10
        ]
        for r in rows(csv_dir, "player.csv")
    }
    birth_by_key: dict[str, str | None] = {}
    for key in set(bbref_birth) | set(fanspo_birth):
        birth_by_key[key] = rec.resolve(
            "birth_date",
            key,
            {Src.BBREF_ROSTER: bbref_birth.get(key), Src.FANSPO: fanspo_birth.get(key)},
        )

    ids.finalise()
    conn.executemany(
        "INSERT OR REPLACE INTO players VALUES (?,?,?,?,?,?,?,?)",
        [
            (
                i.key,
                i.display_name,
                i.bbref_id,
                i.nba_id,
                yos.get(i.bbref_id or ""),
                birth_by_key.get(i.key),
                ",".join(sorted(i.seen_in)),
                None,
            )
            for i in ids.identities.values()
        ],
    )
    counts["players"] = len(ids.identities)

    known = set(ids.identities)

    # ---- contracts and contract years -----------------------------------
    # Key by (player, team): a player traded mid-season has a contract row under
    # each team, and merging them would collide on (contract_id, season_id).
    by_player: dict[tuple[str, str], list[dict[str, str]]] = {}
    for r in rows(csv_dir, "contracts.csv"):
        by_player.setdefault((r["bbref_id"], r["team"]), []).append(r)
    notes = {r["bbref_id"]: r for r in rows(csv_dir, "contract_notes.csv") if r["bbref_id"]}
    name_by_bbref = {i.bbref_id: i.key for i in ids.identities.values() if i.bbref_id}

    cid = 0
    contract_rows, year_rows = [], []
    for (bbref_id, team), seasons in by_player.items():
        player_key = name_by_bbref.get(bbref_id)
        if player_key is None:
            continue
        cid += 1
        note = notes.get(bbref_id, {})
        contract_rows.append(
            (
                cid,
                player_key,
                canonical_team(team),
                None,
                note.get("signed_date") or None,
                "unknown",
                None,
                "unknown",
                None,
                Src.BBREF_CONTRACTS.value,
                None,
            )
        )
        seen_seasons: set[str] = set()
        for s in seasons:
            if s["season_id"] in seen_seasons:
                continue
            seen_seasons.add(s["season_id"])
            year_rows.append(
                (
                    cid,
                    s["season_id"],
                    as_int(s["salary"]),
                    "full",
                    None,
                    None,
                    s["option_type"] or None,
                    None,
                    None,
                )
            )
    conn.executemany("INSERT INTO contracts VALUES (?,?,?,?,?,?,?,?,?,?,?)", contract_rows)
    conn.executemany("INSERT INTO contract_years VALUES (?,?,?,?,?,?,?,?,?)", year_rows)
    counts["contracts"] = len(contract_rows)
    counts["contract_years"] = len(year_rows)

    # ---- cap holds (Fanspo wins on bird_rights) -------------------------
    hold_rows = []
    for hid, r in enumerate(rows(csv_dir, "team_cap_hold.csv"), start=1):
        tri = fanspo_to_tri.get((r["_source_team_ids"].split("|") or [""])[0])
        key = normalise(r.get("description") or "")
        hold_rows.append(
            (
                hid,
                tri,
                key if key in known else None,
                "free_agent",
                as_int(r["capHit"]) or 0,
                r.get("rightType") or None,
                as_int(r.get("qualifyingOfferAmount")),
                SEASON,
                Src.FANSPO.value,
                None,
            )
        )
    conn.executemany("INSERT INTO cap_holds VALUES (?,?,?,?,?,?,?,?,?,?)", hold_rows)
    counts["cap_holds"] = len(hold_rows)

    # ---- draft picks ----------------------------------------------------
    pick_rows = []
    for pid, r in enumerate(rows(csv_dir, "draft_pick.csv"), start=1):
        owner = fanspo_to_tri.get(r.get("teamId") or "")
        # Fanspo's `from` names the originating team; empty means the pick is the
        # owner's own. Without this distinction an override cannot tell LAC's own
        # first from a Toronto first LAC happens to hold.
        origin_raw = (r.get("from") or "").strip()
        origin = canonical_team(origin_raw) if origin_raw and " " not in origin_raw else None
        pick_rows.append(
            (
                pid,
                as_int(r["year"]),
                as_int(r["round"]),
                origin or owner,
                owner,
                0,
                r.get("details") or None,
                Src.FANSPO.value,
                None,
            )
        )
    conn.executemany("INSERT INTO draft_picks VALUES (?,?,?,?,?,?,?,?,?)", pick_rows)
    counts["draft_picks"] = len(pick_rows)

    # ---- trade exceptions (Spotrac wins: original vs available) ---------
    tpe_rows = []
    for tid, r in enumerate(rows(csv_dir, "spotrac_trade_exceptions.csv"), start=1):
        tpe_rows.append(
            (
                tid,
                from_slug(r["team"]),
                as_int(r["original"]) or 0,
                as_int(r["available"]),
                None,
                r.get("expires"),
                r.get("exception_type"),
                r.get("reason"),
                Src.SPOTRAC.value,
                r.get("snapshot_date"),
            )
        )
    conn.executemany("INSERT INTO trade_exceptions VALUES (?,?,?,?,?,?,?,?,?,?)", tpe_rows)
    counts["trade_exceptions"] = len(tpe_rows)

    # ---- hard cap ceilings ----------------------------------------------
    ceiling_rows = []
    for ceid, r in enumerate(rows(csv_dir, "salaryswish_hard_caps.csv"), start=1):
        level = "first_apron" if r["trigger_scope"] == "first" else "second_apron"
        ceiling_rows.append(
            (
                ceid,
                from_display(r["team"]) or from_slug(r.get("team_slug")),
                level,
                None,
                r.get("trigger_category"),
                r.get("trigger_detail"),
                SEASON,
                Src.SALARYSWISH.value,
            )
        )
    conn.executemany("INSERT INTO hard_cap_ceilings VALUES (?,?,?,?,?,?,?,?)", ceiling_rows)
    counts["hard_cap_ceilings"] = len(ceiling_rows)

    # ---- awards ----------------------------------------------------------
    award_rows = []
    for aid, r in enumerate(rows(csv_dir, "awards.csv"), start=1):
        award_rows.append(
            (
                aid,
                name_by_bbref.get(r["bbref_id"]),
                r["bbref_id"],
                r["season_id"],
                r["award"],
                r["tier"],
                Src.BBREF_AWARDS.value,
            )
        )
    conn.executemany("INSERT INTO awards VALUES (?,?,?,?,?,?,?)", award_rows)
    counts["awards"] = len(award_rows)

    # Hand-asserted corrections go on last, so they visibly override scraped data
    # rather than competing with it.
    override_report = apply_pick_overrides(conn, load_pick_overrides())
    counts["pick_overrides_applied"] = len(override_report.applied)

    rec.write(conn)
    conn.executemany(
        "INSERT OR REPLACE INTO ingest_meta VALUES (?,?)",
        [
            ("built_at", datetime.now(UTC).isoformat()),
            ("season", SEASON),
            ("counts", json.dumps(counts)),
            ("resolution", json.dumps(ids.summary)),
            ("reconciliation", json.dumps(rec.summary)),
            ("pick_overrides", json.dumps(override_report.summary)),
        ],
    )
    conn.commit()
    return IngestReport(
        counts=counts,
        resolution=ids.summary,
        reconciliation=rec.summary,
        unresolved=sorted(ids.unresolved)[:20],
        overrides=override_report.summary,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the league database.")
    ap.add_argument("--csv-dir", type=Path, default=DEFAULT_CSV_DIR)
    ap.add_argument("--out", type=Path, default=Path("nbacba.db"))
    args = ap.parse_args()

    report = load(args.csv_dir, args.out)
    for table, n in report.counts.items():
        print(f"  {table:22s} {n:6d}")
    print("\n  identities:", report.resolution)
    print("  reconciliation:", report.reconciliation)
    print("  overrides:", report.overrides)
    print("  unresolved sample:", report.unresolved[:6])
    return 0


if __name__ == "__main__":
    sys.exit(main())
