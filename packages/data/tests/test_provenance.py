"""
Provenance on every query result (task 7.6), on a hand-built database.

The properties worth pinning: a row's own date beats a scrape date, a scrape
date is labelled as one, a row with neither reads as undated rather than
borrowing a plausible date, and provenance covers the rows the filters chose.
"""

from __future__ import annotations

import json

import pytest

from nbadata.db import build, open_readonly
from nbadata.ingest.load import SOURCE_MANIFESTS, source_dates
from nbadata.query import Basis, Filter, Op, Projection, Query, run, snapshot


@pytest.fixture
def conn(tmp_path):
    path = tmp_path / "league.db"
    db = build(path)
    db.executemany(
        "INSERT INTO trade_exceptions (team_key, amount, source, as_of) VALUES (?,?,?,?)",
        [
            ("MIL", 5_000_000, "spotrac_archive", "2025-07-01"),
            ("MIL", 3_000_000, "spotrac_archive", "2026-01-15"),
            ("BOS", 2_000_000, "spotrac_archive", None),
        ],
    )
    db.executemany(
        "INSERT INTO cap_holds (team_key, kind, amount, source) VALUES (?,?,?,?)",
        [("MIL", "fa", 1_000_000, "fanspo"), ("BOS", "fa", 2_000_000, "fanspo")],
    )
    db.execute(
        "INSERT INTO ingest_meta VALUES ('source_dates', ?)",
        (json.dumps({"fanspo": "2026-09-29"}),),
    )
    db.execute("INSERT INTO ingest_meta VALUES ('built_at', '2026-10-02T00:00:00+00:00')")
    db.commit()
    db.close()
    return open_readonly(path)


def test_a_rows_own_date_is_reported_as_a_range(conn):
    result = run(
        conn,
        Query(
            entity="trade_exceptions",
            select=[Projection("amount")],
            filters=[Filter("team", Op.EQ, "MIL")],
        ),
    )
    (observed,) = result.provenance
    assert observed.basis is Basis.ROW
    assert (observed.earliest, observed.latest, observed.rows) == ("2025-07-01", "2026-01-15", 2)


def test_a_live_source_falls_back_to_its_scrape_date_and_says_so(conn):
    result = run(conn, Query(entity="cap_holds", select=[Projection("amount")]))
    (observed,) = result.provenance
    assert observed.basis is Basis.SCRAPED
    assert observed.earliest == "2026-09-29"
    assert "scraped" in observed.describe()


def test_a_row_with_no_date_and_no_scrape_date_is_undated_not_guessed(conn):
    """
    Spotrac's retrieval date is deliberately not recorded, so an undated
    Spotrac row must not borrow it: that date can be 13 months after the fact.
    """
    result = run(
        conn,
        Query(
            entity="trade_exceptions",
            select=[Projection("amount")],
            filters=[Filter("team", Op.EQ, "BOS")],
        ),
    )
    (observed,) = result.provenance
    assert observed.basis is Basis.UNDATED
    assert observed.earliest is None


def test_provenance_covers_the_filtered_rows_not_the_whole_table(conn):
    everything = run(conn, Query(entity="trade_exceptions", select=[Projection("amount")]))
    assert sum(o.rows for o in everything.provenance) == 3
    assert {o.basis for o in everything.provenance} == {Basis.ROW, Basis.UNDATED}


def test_provenance_ignores_limit_and_errs_wide(conn):
    """A SUM reads every filtered row, so a LIMIT must not narrow what is reported."""
    result = run(conn, Query(entity="trade_exceptions", select=[Projection("amount")], limit=1))
    assert result.row_count == 1
    assert sum(o.rows for o in result.provenance) == 3


def test_snapshot_reads_the_build_record_and_leaves_missing_keys_none(conn):
    snap = snapshot(conn)
    assert snap.built_at == "2026-10-02T00:00:00+00:00"
    assert snap.season is None
    assert snap.source_dates == {"fanspo": "2026-09-29"}


def test_source_dates_come_from_the_manifests(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"scraped_at": "2026-09-29T05:59:29+00:00"}))
    (tmp_path / "spotrac_manifest.json").write_text(
        json.dumps({"scraped_at": "2026-09-23T22:51:04+00:00"})
    )
    assert source_dates(tmp_path) == {"fanspo": "2026-09-29"}


def test_spotrac_has_no_scrape_date_by_design():
    """Its scrape date is when the archive was read, not when the page was true."""
    assert "spotrac_archive" not in SOURCE_MANIFESTS
