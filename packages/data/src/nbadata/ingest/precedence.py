"""
Which source wins, per field.

Six sources overlap on several fields and they genuinely disagree. That
redundancy is worth keeping -- it has already caught two real bugs -- but
ingest has to pick one value, and picking silently would bury the conflict.

The ranking below is a *proposal*, recorded so it can be argued with rather
than discovered by reading code. `reconcile.py` reports every disagreement it
resolves, so the cost of a wrong ranking is visible rather than hidden.

Rationale per field is in the comments; the short version is: prefer the source
that publishes the field as structured data over one where it is incidental,
and prefer the more recent snapshot when both are structured.
"""

from __future__ import annotations

from enum import StrEnum


class Src(StrEnum):
    FANSPO = "fanspo"
    BBREF_CONTRACTS = "bbref_contracts"
    BBREF_ROSTER = "bbref_roster"
    BBREF_AWARDS = "bbref_awards"
    SPOTRAC = "spotrac_archive"
    SALARYSWISH = "salaryswish"
    USER_CSV = "user_csv"


# Field -> sources in descending priority. First source that has a value wins.
PRECEDENCE: dict[str, tuple[Src, ...]] = {
    # B-R publishes a six-year grid; Fanspo's payload is current-season only.
    "salary_by_season": (Src.BBREF_CONTRACTS, Src.SPOTRAC, Src.FANSPO),
    # Only B-R carries options per year, via CSS class plus prose. Spotrac's
    # decision calendar corroborates and adds dates.
    "option_type": (Src.BBREF_CONTRACTS, Src.SPOTRAC),
    # Only Spotrac has the guarantee *date*; B-R has the amount.
    "guarantee_date": (Src.SPOTRAC,),
    "guaranteed_amount": (Src.BBREF_CONTRACTS, Src.SPOTRAC),
    # B-R roster's Exp column is the published figure; anything else is derived.
    "years_of_service": (Src.BBREF_ROSTER,),
    # Both carry it; B-R is the one we have per-player with an id attached.
    "birth_date": (Src.BBREF_ROSTER, Src.FANSPO),
    # Fanspo carries rightType directly (Bird / Early Bird / Non-Bird).
    "bird_rights": (Src.FANSPO, Src.SPOTRAC),
    # Spotrac distinguishes original vs available, so partial use is visible.
    "trade_exception": (Src.SPOTRAC, Src.FANSPO),
    # Fanspo's details field carries the full conditional prose.
    "draft_pick_protection": (Src.FANSPO,),
    # Only SalarySwish ties a ceiling to its triggering transaction.
    "hard_cap_ceiling": (Src.SALARYSWISH,),
    # Only SalarySwish publishes cash with direction.
    "cash_in_trade": (Src.SALARYSWISH,),
    # Fanspo's figures are actuals back to 2011-12; the user CSVs are forward
    # projections, which Phase 4 must not validate history against.
    "season_constants": (Src.FANSPO, Src.USER_CSV),
    "signing_date": (Src.BBREF_CONTRACTS, Src.FANSPO),
    "awards": (Src.BBREF_AWARDS,),
}


def winner(field: str, available: set[Src]) -> Src | None:
    for source in PRECEDENCE.get(field, ()):
        if source in available:
            return source
    return None
