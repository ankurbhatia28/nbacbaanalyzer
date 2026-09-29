"""
Ingest against the real scraper output.

Skipped when the CSVs are absent so a fresh clone still passes; run locally and
in CI after the scrapers have been executed.
"""

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
    assert report["reconciliation"]["disagreements"] == 0
    assert report["reconciliation"]["agreements"] > 500
