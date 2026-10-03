"""
Ingest against the real scraper output.

Skipped when the CSVs are absent so a fresh clone still passes; run locally and
in CI after the scrapers have been executed.
"""

import sqlite3
from pathlib import Path

import pytest

from nbadata.db import open_readonly
from nbadata.ingest.load import load

CSV_DIR = Path(__file__).resolve().parents[3] / "scraper" / "out"
pytestmark = pytest.mark.skipif(
    not (CSV_DIR / "contracts.csv").exists(), reason="scraper output not present"
)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    db = tmp_path_factory.mktemp("db") / "nbacba.db"
    report = load(CSV_DIR, db)
    return db, report


def test_all_thirty_teams_load(built):
    db, _ = built
    assert open_readonly(db).execute("SELECT COUNT(*) FROM teams").fetchone()[0] == 30


def test_identities_cross_link_the_two_id_spaces(built):
    _, report = built
    res = report["resolution"]
    assert res["cross_linked"] > 500
    assert res["unresolved"] <= 5  # a handful of genuine absences, not a broken join


def test_milwaukee_holds_both_ceilings(built):
    """The case the domain model was reshaped around, now end to end."""
    db, _ = built
    rows = (
        open_readonly(db)
        .execute(
            "SELECT apron_level, trigger_category FROM hard_cap_ceilings "
            "WHERE team_key='MIL' ORDER BY apron_level"
        )
        .fetchall()
    )
    levels = {r["apron_level"] for r in rows}
    assert levels == {"first_apron", "second_apron"}


def test_bird_rights_survive_ingest(built):
    db, _ = built
    kinds = {
        r["bird_rights"]
        for r in open_readonly(db).execute(
            "SELECT DISTINCT bird_rights FROM cap_holds WHERE bird_rights IS NOT NULL"
        )
    }
    assert {"Bird", "Early Bird", "Non-Bird"} <= kinds


def test_options_are_preserved_per_season(built):
    db, _ = built
    kinds = dict(
        open_readonly(db)
        .execute(
            "SELECT option_kind, COUNT(*) FROM contract_years "
            "WHERE option_kind IS NOT NULL GROUP BY option_kind"
        )
        .fetchall()
    )
    assert kinds.get("team", 0) > 200
    assert kinds.get("player", 0) > 50


def test_birth_dates_agree_across_sources(built):
    """Two independent sources, same fact. Any disagreement is a data problem."""
    _, report = built
    # Only birth dates: since D18 the reconciler also reports current-season
    # salary overrides, which are expected and tested on their own below.
    assert report["reconciliation"].get("birth_date", 0) == 0
    assert report["reconciliation"]["agreements"] > 500


def test_no_team_sits_above_its_own_hard_cap(tmp_path):
    """
    A cross-source invariant (D18): salaries come from one source and hard-cap
    ceilings from another, and a hard-capped team cannot exceed its ceiling.
    On Basketball-Reference's current-season figures MIN and PHI did, which is
    what showed that source reading as a projection rather than a payroll.

    Apron salary here is contracts + dead money + restricted free agents'
    qualifying offers, per Art. VII §2(e)(1).
    """
    if not (CSV_DIR / "team_payroll_player.csv").exists():
        pytest.skip("scraper output not present")
    load(CSV_DIR, tmp_path / "league.db")
    conn = sqlite3.connect(tmp_path / "league.db")
    over = conn.execute(
        """
        WITH sal AS (SELECT c.team_key t, SUM(y.cap_figure) s FROM contracts c
                     JOIN contract_years y USING (contract_id)
                     WHERE y.season_id = '2026-2027' GROUP BY 1),
             dead AS (SELECT team_key t, SUM(amount) d FROM dead_money GROUP BY 1),
             qo AS (SELECT team_key t, SUM(qualifying_offer) q FROM cap_holds
                    WHERE bird_rights LIKE 'Restricted%' GROUP BY 1),
             lim AS (SELECT h.team_key t, MIN(CASE h.apron_level WHEN 'first_apron'
                            THEN s.first_apron ELSE s.second_apron END) c
                     FROM hard_cap_ceilings h JOIN seasons s ON s.season_id = h.season_id
                     GROUP BY 1)
        SELECT sal.t, sal.s + COALESCE(d, 0) + COALESCE(q, 0), lim.c
        FROM sal JOIN lim ON lim.t = sal.t
        LEFT JOIN dead ON dead.t = sal.t LEFT JOIN qo ON qo.t = sal.t
        WHERE sal.s + COALESCE(d, 0) + COALESCE(q, 0) > lim.c
        """
    ).fetchall()
    assert over == []


def test_every_current_season_override_is_reported_not_silent(tmp_path):
    """D18 overrules Basketball-Reference; each overruling is a disagreement row."""
    if not (CSV_DIR / "team_payroll_player.csv").exists():
        pytest.skip("scraper output not present")
    load(CSV_DIR, tmp_path / "league.db")
    conn = sqlite3.connect(tmp_path / "league.db")
    dropped = conn.execute(
        "SELECT subject FROM disagreements WHERE field = 'salary_current_season' "
        "AND chosen_value = 'not on the current payroll'"
    ).fetchall()
    assert ("draymond green@GSW",) in dropped
    # Nobody dropped is still on a current-season contract.
    still = conn.execute(
        "SELECT COUNT(*) FROM contracts c JOIN contract_years y USING (contract_id) "
        "WHERE y.season_id = '2026-2027' AND c.player_key || '@' || c.team_key IN "
        "(SELECT subject FROM disagreements WHERE chosen_value = 'not on the current payroll')"
    ).fetchone()[0]
    assert still == 0
