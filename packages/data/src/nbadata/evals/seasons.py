"""Season constants for the eval run, from the scraped cap history."""

from __future__ import annotations

import csv
from pathlib import Path

from engine.provenance import Provenance, Source
from engine.season import Season

DEFAULT = Path(__file__).resolve().parents[5] / "scraper" / "out" / "salary_cap_figure.csv"
BASE_SEASON = "2023-2024"
"""The Expanded exception scales $7.5m against this season's cap (Art. VII 6(j)(1)(iv))."""


def _int(value: str | None) -> int:
    return int(float(value)) if value else 0


def load_seasons(path: Path | None = None) -> tuple[dict[str, Season], int]:
    """Returns the seasons by id and the 2023-24 cap the Expanded exception needs."""
    source = path or DEFAULT
    seasons: dict[str, Season] = {}
    if not source.exists():
        return seasons, 0
    with source.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if not row.get("cap"):
                continue
            seasons[row["seasonId"]] = Season(
                season_id=row["seasonId"],
                salary_cap=_int(row["cap"]),
                tax_level=_int(row["tax"]),
                first_apron=_int(row["apron"]),
                second_apron=_int(row["apronTwo"]) or _int(row["apron"]),
                non_taxpayer_mle=_int(row["nonTaxpayerMLE"]),
                taxpayer_mle=_int(row["taxpayerMLE"]),
                room_mle=_int(row["roomMLE"]),
                bi_annual_exception=_int(row["biAnnualEx"]),
                provenance=Provenance(Source.FANSPO),
            )
    base = seasons[BASE_SEASON].salary_cap if BASE_SEASON in seasons else 0
    return seasons, base
