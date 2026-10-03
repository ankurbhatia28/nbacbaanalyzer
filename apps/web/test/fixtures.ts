import type { AnswerCard } from "@/lib/card";

/** A data answer shaped like the first live run's card (7.0), text shortened. */
export function dataCard(overrides: Partial<AnswerCard> = {}): AnswerCard {
  return {
    schema: 1,
    question: "How much are the Nuggets committed for in 2026-27?",
    status: "answered",
    verified: true,
    text: "Denver is committed for **$221,069,148** in 2026-27 (Art. I §1(uuu)).",
    citations: ["Art. I §1(uuu)", "Art. VII §4"],
    quotes: [
      {
        citation: "Art. VII §4",
        text: "Section 4 text.",
        tool: "fetch_provision",
        pdf_page: 235,
        printed_page: 211,
        cited_in_answer: false,
      },
      {
        citation: "Art. I §1(uuu)",
        text: "“Team Salary” means the sum of all Salaries...",
        tool: "fetch_provision",
        pdf_page: 35,
        printed_page: 11,
        cited_in_answer: true,
      },
    ],
    figures: [
      {
        sql: 'SELECT SUM(y.cap_figure) AS "total_committed" FROM ... WHERE c.team_key = ?',
        params: ["Denver Nuggets"],
        columns: ["total_committed"],
        rows: [{ total_committed: null }],
        provenance: [],
        in_answer: [],
      },
      {
        sql: 'SELECT SUM(y.cap_figure) AS "total_committed" FROM ... WHERE c.team_key = ?',
        params: ["DEN", "2026-2027"],
        columns: ["total_committed", "num_players"],
        rows: [{ total_committed: 221069148, num_players: 14 }],
        provenance: [
          {
            source: "bbref_contracts",
            rows: 14,
            basis: "scraped",
            earliest: "2026-09-29",
            latest: "2026-09-29",
          },
        ],
        in_answer: ["$221,069,148"],
      },
    ],
    assumptions: [],
    warnings: [],
    refusal_basis: null,
    dataset: {
      built_at: "2026-10-03T03:26:30+00:00",
      season: "2026-2027",
      source_dates: { fanspo: "2026-09-29", salaryswish: "2026-09-30" },
    },
    cost_usd: 0.1248,
    seconds: 21.41,
    ...overrides,
  };
}
