"""
The queryable surface (task 2.5).

Every entity is a *fixed view* with its joins already written. The model never
chooses a table, never writes a join, and never names a column that is not
listed here. That is the whole safety argument of ADR-002: a generated query
that joins wrong produces a plausible number with no error anywhere, which is
the same invisible failure as letting the model do arithmetic.

Adding a capability is a code change with tests, not a prompt change.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FieldType(StrEnum):
    TEXT = "text"
    INTEGER = "integer"
    REAL = "real"
    DATE = "date"


@dataclass(frozen=True, slots=True)
class Field:
    name: str
    type: FieldType
    sql: str
    description: str


@dataclass(frozen=True, slots=True)
class Entity:
    name: str
    source_sql: str
    description: str
    fields: tuple[Field, ...]
    source_column: str = "source"
    """
    Where the figure-bearing table records its source (task 7.6).

    Named per entity because a joined view has several tables, and the
    provenance worth reporting is that of the table the figures come from --
    a salary's, not the player record it was joined to.
    """
    as_of_column: str | None = None
    """
    The per-row observation date, where the table has one.

    None for tables whose rows carry no date. Their provenance falls back to
    when the source was scraped, and says that is what it is.
    """

    def field(self, name: str) -> Field | None:
        return next((f for f in self.fields if f.name == name), None)

    @property
    def field_names(self) -> list[str]:
        return [f.name for f in self.fields]


_PLAYER_CONTRACT_SEASONS = Entity(
    name="contract_seasons",
    description=(
        "One row per player per contract season: salary, option type and team. "
        "Use for questions about salaries, options, or who is under contract when."
    ),
    source_sql="""
        contract_years y
        JOIN contracts c ON c.contract_id = y.contract_id
        JOIN players p ON p.player_key = c.player_key
    """,
    fields=(
        Field("player", FieldType.TEXT, "p.display_name", "Player name"),
        Field("player_key", FieldType.TEXT, "p.player_key", "Normalised join key"),
        Field("team", FieldType.TEXT, "c.team_key", "Team abbreviation, e.g. MIL"),
        Field("season", FieldType.TEXT, "y.season_id", "Season, e.g. 2026-2027"),
        Field("salary", FieldType.INTEGER, "y.cap_figure", "Cap figure for that season"),
        Field("option_kind", FieldType.TEXT, "y.option_kind", "team, player or eto; null if none"),
        Field(
            "guarantee_kind",
            FieldType.TEXT,
            "y.guarantee_kind",
            "full, partial, none or unknown. No source scraped so far carries "
            "guarantee structure, so this is 'unknown' for every row today; "
            "do not read it as 'fully guaranteed'",
        ),
        Field("contract_type", FieldType.TEXT, "c.contract_type", "Contract classification"),
        Field("signed_date", FieldType.DATE, "c.signed_date", "When the contract was signed"),
        Field(
            "years_of_service",
            FieldType.INTEGER,
            "p.years_of_service",
            "Seasons completed before this one",
        ),
    ),
    source_column="c.source",
    as_of_column="c.as_of",
)

_CAP_HOLDS = Entity(
    name="cap_holds",
    description=(
        "Cap holds by team, including Bird rights classification. Use for "
        "questions about Bird / Early Bird / Non-Bird rights and free agent holds."
    ),
    source_sql="cap_holds h LEFT JOIN players p ON p.player_key = h.player_key",
    fields=(
        Field(
            "player",
            FieldType.TEXT,
            "COALESCE(p.display_name, h.player_key)",
            "Player name if resolved",
        ),
        Field("team", FieldType.TEXT, "h.team_key", "Team abbreviation"),
        Field("amount", FieldType.INTEGER, "h.amount", "Hold amount against the cap"),
        Field(
            "bird_rights", FieldType.TEXT, "h.bird_rights", "Bird, Early Bird, Non-Bird, or other"
        ),
        Field("kind", FieldType.TEXT, "h.kind", "Hold category"),
        Field("qualifying_offer", FieldType.INTEGER, "h.qualifying_offer", "QO amount if any"),
        Field("season", FieldType.TEXT, "h.season_id", "Season the hold applies to"),
    ),
    source_column="h.source",
    as_of_column="h.as_of",
)

_HARD_CAP_CEILINGS = Entity(
    name="hard_cap_ceilings",
    description=(
        "Hard-cap ceilings a team's own transactions imposed on it, with the "
        "triggering transaction. A team may hold more than one; the lowest binds. "
        "Distinct from where a team's salary currently sits."
    ),
    source_sql="hard_cap_ceilings",
    fields=(
        Field("team", FieldType.TEXT, "team_key", "Team abbreviation"),
        Field("apron_level", FieldType.TEXT, "apron_level", "first_apron or second_apron"),
        Field(
            "trigger_category",
            FieldType.TEXT,
            "trigger_category",
            "Kind of transaction that set it",
        ),
        Field("trigger_detail", FieldType.TEXT, "trigger_detail", "The specific transaction"),
        Field("season", FieldType.TEXT, "season_id", "Season the ceiling applies to"),
    ),
    source_column="source",
)

_DRAFT_PICKS = Entity(
    name="draft_picks",
    description=(
        "Draft pick ownership and protection prose. Forfeitures are NOT represented: "
        "the snapshot predates the September 2026 Clippers penalty."
    ),
    source_sql="draft_picks",
    fields=(
        Field("year", FieldType.INTEGER, "year", "Draft year"),
        Field("round", FieldType.INTEGER, "round", "1 or 2"),
        Field("team", FieldType.TEXT, "owner_team_key", "Current owner"),
        Field(
            "original_team", FieldType.TEXT, "original_team_key", "Team the pick originated with"
        ),
        # NOT POPULATED. No source we scrape encodes forfeiture, and the Fanspo
        # snapshot predates the September 2026 Clippers penalty, so LAC still shows
        # 2029-2033 firsts it no longer holds. A zero result here means "we have no
        # forfeiture data", not "no team has forfeited picks".
        Field("forfeited", FieldType.INTEGER, "forfeited", "Always 0 -- no source populates this"),
        Field("protection_text", FieldType.TEXT, "protection_text", "Protection prose, if any"),
    ),
    source_column="source",
    as_of_column="as_of",
)

_TRADE_EXCEPTIONS = Entity(
    name="trade_exceptions",
    description="Traded player exceptions, with original and remaining amounts.",
    source_sql="trade_exceptions",
    fields=(
        Field("team", FieldType.TEXT, "team_key", "Holding team"),
        Field("amount", FieldType.INTEGER, "amount", "Original amount"),
        Field("available", FieldType.INTEGER, "available", "Remaining amount"),
        Field("expires", FieldType.DATE, "expires", "Expiry date"),
        Field("kind", FieldType.TEXT, "kind", "Exception type"),
        Field("reason", FieldType.TEXT, "reason", "Transaction that created it"),
    ),
    source_column="source",
    as_of_column="as_of",
)

_AWARDS = Entity(
    name="awards",
    description=(
        "All-NBA, Defensive Player of the Year and MVP -- the three awards that "
        "constitute the CBA's Higher Max Criteria. All-Star is deliberately absent."
    ),
    source_sql="awards a LEFT JOIN players p ON p.player_key = a.player_key",
    fields=(
        Field("player", FieldType.TEXT, "COALESCE(p.display_name, a.bbref_id)", "Player name"),
        Field("season", FieldType.TEXT, "a.season_id", "Season"),
        Field("award", FieldType.TEXT, "a.award", "All-NBA, DPOY or MVP"),
        Field("tier", FieldType.TEXT, "a.tier", "1st/2nd/3rd for All-NBA, else Winner"),
    ),
    source_column="a.source",
)

_SEASONS = Entity(
    name="seasons",
    description="League-wide thresholds per season: cap, tax, both aprons, exceptions.",
    source_sql="seasons",
    fields=(
        Field("season", FieldType.TEXT, "season_id", "Season"),
        Field("salary_cap", FieldType.INTEGER, "salary_cap", "Salary cap"),
        Field("tax_level", FieldType.INTEGER, "tax_level", "Luxury tax line"),
        Field("first_apron", FieldType.INTEGER, "first_apron", "First apron level"),
        Field("second_apron", FieldType.INTEGER, "second_apron", "Second apron level"),
        Field("non_taxpayer_mle", FieldType.INTEGER, "non_taxpayer_mle", "Non-taxpayer MLE"),
        Field("taxpayer_mle", FieldType.INTEGER, "taxpayer_mle", "Taxpayer MLE"),
    ),
    source_column="source",
)

ENTITIES: dict[str, Entity] = {
    e.name: e
    for e in (
        _PLAYER_CONTRACT_SEASONS,
        _CAP_HOLDS,
        _HARD_CAP_CEILINGS,
        _DRAFT_PICKS,
        _TRADE_EXCEPTIONS,
        _AWARDS,
        _SEASONS,
    )
}


def describe_catalog() -> str:
    """Human- and model-readable listing, for tool descriptions and refusals."""
    lines = []
    for entity in ENTITIES.values():
        lines.append(f"{entity.name}: {entity.description}")
        lines.append("  fields: " + ", ".join(entity.field_names))
    return "\n".join(lines)
