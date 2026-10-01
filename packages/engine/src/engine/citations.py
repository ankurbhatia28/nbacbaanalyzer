"""
Citations into the CBA (task 3.17).

Every rule the engine implements names the provision it came from. This table is
the join between the deterministic engine and the retrieval layer: the engine
emits a violation code, this maps it to an Article and Section, and retrieval
fetches that text verbatim. The model quotes; it never chooses which rule
applies. That is why citations here are right where a pure-RAG system's would be
plausible.

Page numbers are the PDF's own (676 pages, 2023 CBA).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Citation:
    article: str
    section: str
    page: int
    title: str

    def __str__(self) -> str:
        return f"Article {self.article}, Section {self.section} (p. {self.page})"

    @property
    def short(self) -> str:
        return f"Art. {self.article} §{self.section}"


# -- Article VII, Section 2: cap, tax and apron levels ---------------------
APRON_LEVELS = Citation("VII", "2(e)(1)(iii)", 195, "First and Second Apron Levels")
APRON_TEAM_SALARY = Citation("VII", "2(e)(1)", 211, "Apron Team Salary computation")
TRANSACTION_PROHIBITION = Citation(
    "VII",
    "2(e)(2)(i)(A)",
    211,
    "A Team may not engage in a transaction set forth in the Transaction Restrictions "
    "Table if, immediately following such transaction, the Team's Apron Team Salary "
    "would exceed the Applicable Apron Level",
)
"""The forward-looking prohibition: what a team may not do at all.

Distinct from TRANSACTION_RESTRICTIONS below, which is the ceiling that attaches
*after* a permitted transaction. Citing (B) for a refusal to permit would point a
reader at the wrong rule.
"""
TRANSACTION_RESTRICTIONS = Citation(
    "VII",
    "2(e)(2)(i)(B)",
    211,
    "A team engaging in a listed transaction may not exceed the applicable apron level "
    "for the remainder of the Salary Cap Year",
)
TRANSACTION_RESTRICTIONS_TABLE = Citation(
    "VII", "2(e)(4)", 214, "Transaction Restrictions Table, rows A-K"
)
SUBSEQUENT_YEAR_RESTRICTION = Citation(
    "VII",
    "2(e)(2)(ii)",
    212,
    "Rows E-J executed after the Regular Season bind the following Salary Cap Year",
)
DRAFT_PICK_PENALTY = Citation("VII", "2(f)", 219, "Second Apron Team draft pick penalty")

# -- Article VII, Section 3: determination of salary ----------------------
OVER_38_RULE = Citation(
    "VII",
    "3(a)(2)",
    222,
    "Over 38 Rule -- four or more Seasons including one after the player reaches 38",
)

# -- Article VII, Section 6: exceptions -----------------------------------
TAXPAYER_MLE = Citation("VII", "6(f)", 261, "Taxpayer Mid-Level Salary Exception")
NON_TAXPAYER_MLE = Citation("VII", "6(e)", 262, "Non-Taxpayer Mid-Level Salary Exception")
TPE_STANDARD = Citation("VII", "6(j)(1)(i)", 264, "Standard Traded Player Exception")
TPE_AGGREGATED = Citation("VII", "6(j)(1)(ii)", 264, "Aggregated Standard Traded Player Exception")
TPE_TRANSITION = Citation("VII", "6(j)(1)(iii)", 265, "Transition Traded Player Exception")
TPE_EXPANDED = Citation("VII", "6(j)(1)(iv)", 265, "Expanded Traded Player Exception")
TPE_ROOM = Citation("VII", "6(j)(1)(v)", 265, "Room Under Salary Cap Plus $250,000")
TPE_ROOM_TEAM_ALTERNATIVE = Citation(
    "VII",
    "6(j)(2)",
    266,
    "A team below the cap may instead use the Transition or Expanded exception",
)
TPE_ALLOWANCE_REMOVED_AT_APRON = Citation(
    "VII",
    "6(j)(3)",
    266,
    "The $250,000 allowance is reduced to $0 if post-assignment Apron Team Salary "
    "would exceed the First Apron Level",
)
AGGREGATION_TWO_MONTH_BAR = Citation(
    "VII",
    "6(j)(4)(i)",
    266,
    "A contract acquired via an Exception may not be aggregated for two months",
)
AGGREGATION_THREE_PLAYER_RULE = Citation(
    "VII", "6(j)(4)(ii)", 266, "Aggregating three or more players"
)

# -- Article VII, Section 8: trade rules ----------------------------------
TRADE_RULES = Citation("VII", "8", 284, "Trade Rules")
CASH_IN_TRADE = Citation("VII", "8(a)", 284, "Cash paid in connection with a trade")
SIGN_AND_TRADE = Citation("VII", "8(e)(1)", 287, "Sign-and-trade transactions")
ROOKIE_EXTENSION_TRADE_RULE = Citation(
    "VII",
    "8(g)",
    288,
    "A traded rookie-scale extension is valued at the average of its remaining years, "
    "for the acquiring team's Room only",
)

# -- Article XI: restricted free agency -----------------------------------
ARENAS_OFFER_SHEET_LIMIT = Citation(
    "XI",
    "5(d)(i)",
    346,
    "Offer Sheet to a restricted free agent with one or two Years of Service may not "
    "exceed the Non-Taxpayer MLE in the first Salary Cap Year",
)
ARENAS_THIRD_YEAR = Citation("XI", "5(d)(ii)", 347, "Third-year balloon and its conditions")
ARENAS_DEEMED_AVERAGE = Citation(
    "XI",
    "5(d)(iii)",
    347,
    "For the offering team's Room, first-year Salary is deemed the average of all years",
)

# -- Article I: definitions ------------------------------------------------
DEFINITIONS = Citation("I", "1", 25, "Definitions")
GENERALLY_RECOGNIZED_HONORS = Citation("I", "1(cc)", 27, "Generally Recognized League Honors")

# -- Article II: contracts and maximum salary ------------------------------
HIGHER_MAX_CRITERIA = Citation(
    "II",
    "7",
    60,
    "Higher Max Criteria -- All-NBA, Defensive Player of the Year or MVP",
)
ROOKIE_SCALE_EXTENSION_TIERS = Citation("II", "7(d)", 65, "Rookie Scale Extension maximum tiers")

ALL_CITATIONS: tuple[Citation, ...] = tuple(
    value
    for name, value in list(globals().items())
    if isinstance(value, Citation) and name.isupper()
)
