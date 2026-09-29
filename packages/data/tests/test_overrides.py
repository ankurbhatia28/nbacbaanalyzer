"""Hand-asserted facts must be precise, cited, and loud when they miss."""

from pathlib import Path

import pytest

from nbadata.db import build
from nbadata.ingest.overrides import (
    OverrideError,
    PickOverride,
    apply_pick_overrides,
    load_pick_overrides,
)

REAL_FILE = Path(__file__).resolve().parents[3] / "data" / "overrides" / "pick_overrides.csv"


def write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "ov.csv"
    path.write_text(body, encoding="utf-8")
    return path


HEADER = "year,round,original_team,owner_team,action,citation_url,note,asserted_on\n"


def test_a_row_without_a_citation_is_rejected():
    """An uncited assertion is indistinguishable from a guess."""
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        path = write(Path(d), HEADER + "2030,1,LAC,LAC,forfeit,,no source,2026-09-29\n")
        with pytest.raises(OverrideError, match="citation"):
            load_pick_overrides(path)


def test_an_unsupported_action_is_rejected_with_the_supported_list():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        path = write(Path(d), HEADER + "2030,1,LAC,LAC,delete,https://x/,n,2026-09-29\n")
        with pytest.raises(OverrideError, match="forfeit"):
            load_pick_overrides(path)


def test_missing_file_is_not_an_error():
    assert load_pick_overrides(Path("/nonexistent/ov.csv")) == []


def test_an_override_matching_nothing_is_reported_not_ignored(tmp_path):
    """
    Usually means the scraped data changed shape and the assertion now points at
    nothing -- exactly when you want to hear about it.
    """
    conn = build(tmp_path / "t.db")
    conn.execute("INSERT INTO draft_picks VALUES (1,2030,1,'LAC','LAC',0,NULL,'fanspo',NULL)")
    report = apply_pick_overrides(
        conn, [PickOverride(2099, 1, "XXX", "XXX", "forfeit", "https://x/", "n", "2026-09-29")]
    )
    assert report.summary == {"loaded": 1, "applied": 0, "unmatched": 1}


def test_an_override_marks_only_the_pick_it_names(tmp_path):
    """
    The precision that matters: LAC held its own 2029 first AND an Indiana pick.
    Only the Indiana one was forfeited. A year-wide override would have wrongly
    stripped both.
    """
    conn = build(tmp_path / "t.db")
    conn.execute("INSERT INTO draft_picks VALUES (1,2029,1,'LAC','LAC',0,NULL,'fanspo',NULL)")
    conn.execute("INSERT INTO draft_picks VALUES (2,2029,1,'IND','LAC',0,NULL,'fanspo',NULL)")
    conn.execute("INSERT INTO draft_picks VALUES (3,2029,1,'IND','IND',0,NULL,'fanspo',NULL)")
    report = apply_pick_overrides(
        conn,
        [PickOverride(2029, 1, "IND", "LAC", "forfeit", "https://x/", "penalty", "2026-09-29")],
    )
    assert report.summary["applied"] == 1
    rows = {
        (origin, owner): forfeited
        for origin, owner, forfeited in conn.execute(
            "SELECT original_team_key, owner_team_key, forfeited FROM draft_picks WHERE year=2029"
        )
    }
    assert rows[("LAC", "LAC")] == 0  # the Clippers' own pick, untouched
    assert rows[("IND", "LAC")] == 1  # the Indiana pick they held, forfeited
    assert rows[("IND", "IND")] == 0  # Indiana's own pick, untouched


def test_applied_override_records_its_citation(tmp_path):
    conn = build(tmp_path / "t.db")
    conn.execute("INSERT INTO draft_picks VALUES (1,2030,1,'LAC','LAC',0,NULL,'fanspo',NULL)")
    apply_pick_overrides(
        conn,
        [
            PickOverride(
                2030,
                1,
                "LAC",
                "LAC",
                "forfeit",
                "https://pr.nba.com/x",
                "League penalty",
                "2026-09-29",
            )
        ],
    )
    text = conn.execute("SELECT protection_text FROM draft_picks").fetchone()[0]
    assert "OVERRIDE forfeit" in text
    assert "https://pr.nba.com/x" in text


@pytest.mark.skipif(not REAL_FILE.exists(), reason="override file absent")
def test_the_committed_override_file_is_valid_and_cited():
    overrides = load_pick_overrides(REAL_FILE)
    assert len(overrides) == 5
    assert all(o.citation_url.startswith("https://") for o in overrides)
    assert {o.year for o in overrides} == {2029, 2030, 2031, 2032, 2033}
    # 2029 is the Indiana pick, not the Clippers' own -- per RealGM's counts.
    by_year = {o.year: o.original_team for o in overrides}
    assert by_year[2029] == "IND"
    assert by_year[2030] == "LAC"
