"""Reference season and boundary helpers."""

from __future__ import annotations

from engine.provenance import Provenance, Source
from engine.season import Season

SEASON_2026_27 = Season(
    season_id="2026-2027",
    salary_cap=166_000_000,
    tax_level=201_690_000,
    first_apron=210_690_000,
    second_apron=223_690_000,
    non_taxpayer_mle=14_104_000,
    taxpayer_mle=5_685_000,
    room_mle=8_781_000,
    bi_annual_exception=5_134_000,
    minimum_scale={
        0: 1_272_870,
        1: 2_048_494,
        2: 2_296_274,
        3: 2_378_870,
        4: 2_461_463,
        5: 2_656_302,
        6: 2_851_140,
        7: 3_045_979,
        8: 3_240_818,
        9: 3_267_652,
        10: 3_615_000,
    },
    rookie_scale={1: 11_521_600, 2: 10_308_600, 14: 4_500_000, 30: 2_600_000},
    provenance=Provenance(Source.FIXTURE, note="mirrors real 2026-27 figures"),
)


def just_below(threshold: int, by: int = 1) -> int:
    """A value that must not trip a threshold test."""
    return threshold - by


def just_above(threshold: int, by: int = 1) -> int:
    """A value that must trip it."""
    return threshold + by
