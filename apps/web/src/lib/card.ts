/**
 * The answer card, as the API sends it.
 *
 * Mirrors `packages/agent/src/agent/card.py`, which is the definition; this
 * file follows it. `SCHEMA_VERSION` is checked on every card, so a change on
 * the Python side that this file has not caught up with fails loudly instead
 * of rendering half the fields.
 */

export const SCHEMA_VERSION = 1;

export type Status = "answered" | "refused" | "clarification" | "unavailable";

export type WarningKind =
  | "unsourced_figures"
  | "unsupported"
  | "exhausted_rounds"
  | "unknown_values"
  | "undated_rows"
  | "fallback_model";

export interface Quote {
  citation: string;
  text: string;
  tool: string;
  pdf_page: number | null;
  printed_page: number | null;
  cited_in_answer: boolean;
}

export type Basis = "row" | "scraped" | "undated";

export interface Observed {
  source: string;
  rows: number;
  basis: Basis;
  earliest: string | null;
  latest: string | null;
}

export type Cell = string | number | null;

export interface Figure {
  sql: string;
  params: Cell[];
  columns: string[];
  rows: Record<string, Cell>[];
  provenance: Observed[];
  in_answer: string[];
}

export interface CardWarning {
  kind: WarningKind;
  message: string;
  detail: string[];
}

export interface Dataset {
  built_at: string | null;
  season: string | null;
  source_dates: Record<string, string>;
}

export interface AnswerCard {
  schema: number;
  question: string;
  status: Status;
  verified: boolean;
  text: string;
  citations: string[];
  quotes: Quote[];
  figures: Figure[];
  assumptions: string[];
  warnings: CardWarning[];
  refusal_basis: string | null;
  dataset: Dataset | null;
  cost_usd: number | null;
  seconds: number | null;
  /**
   * Players a validation question named, for the trade builder (7.4). Optional:
   * cards from before it, permalinks included, do not carry it.
   */
  trade?: { players: string[] } | null;
}

export class SchemaMismatch extends Error {
  constructor(public readonly got: unknown) {
    super(
      `The API sent answer-card schema ${String(got)}; this page understands ${SCHEMA_VERSION}. ` +
        "Reload the page, and if that does not help the web app needs updating.",
    );
  }
}

/** Accept a card only if it is the version this renderer was written for. */
export function parseCard(payload: unknown): AnswerCard {
  const schema = (payload as { schema?: unknown } | null)?.schema;
  if (schema !== SCHEMA_VERSION) throw new SchemaMismatch(schema);
  return payload as AnswerCard;
}
