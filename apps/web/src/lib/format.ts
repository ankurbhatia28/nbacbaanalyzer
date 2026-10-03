/**
 * Formatting for the card: source names, dates, cells, and the links that tie
 * a number in the answer to the query behind it (7.3).
 *
 * Pure functions, so the parts that decide what a reader is told can be tested
 * without rendering anything.
 */

import type { Cell, Dataset, Figure, Observed, Quote } from "./card";

export const SOURCE_NAMES: Record<string, string> = {
  fanspo: "Fanspo",
  bbref_contracts: "Basketball-Reference contracts",
  bbref_roster: "Basketball-Reference rosters",
  bbref_awards: "Basketball-Reference awards",
  spotrac_archive: "Spotrac, via the Wayback Machine",
  salaryswish: "SalarySwish",
};

export function sourceName(source: string): string {
  return SOURCE_NAMES[source] ?? source;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/**
 * "2026-09-29" or a full ISO timestamp -> "29 Sep 2026", in UTC. Unparseable
 * stays as given. Written out rather than left to Intl, whose month names
 * differ between ICU builds ("Sep" or "Sept"), which also makes server and
 * browser renders disagree.
 */
export function formatDate(iso: string): string {
  const parsed = new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return `${parsed.getUTCDate()} ${MONTHS[parsed.getUTCMonth()]} ${parsed.getUTCFullYear()}`;
}

function dateRange(earliest: string | null, latest: string | null): string {
  if (!earliest) return "";
  if (!latest || latest === earliest) return formatDate(earliest);
  return `${formatDate(earliest)} – ${formatDate(latest)}`;
}

/**
 * One source's share of a result, in words. The three bases read differently
 * on purpose: a scrape date says when we looked, not when the fact last
 * changed, and an undated row says so rather than borrowing a date.
 */
export function describeObserved(o: Observed): string {
  const rows = `${o.rows.toLocaleString("en-US")} ${o.rows === 1 ? "row" : "rows"}`;
  const when =
    o.basis === "undated"
      ? "date unknown"
      : o.basis === "scraped"
        ? `scraped ${dateRange(o.earliest, o.latest)}`
        : `as of ${dateRange(o.earliest, o.latest)}`;
  return `${sourceName(o.source)} · ${when} · ${rows}`;
}

/** "2026-2027" -> "2026-27". */
export function shortSeason(season: string): string {
  const match = /^(\d{4})-(\d{2})(\d{2})$/.exec(season);
  return match ? `${match[1]}-${match[3]}` : season;
}

export function datasetSummary(dataset: Dataset): string {
  const parts: string[] = [];
  if (dataset.season) parts.push(`${shortSeason(dataset.season)} season`);
  const dates = Object.values(dataset.source_dates).sort();
  if (dates.length) parts.push(`sources read ${dateRange(dates[0]!, dates[dates.length - 1]!)}`);
  if (dataset.built_at) parts.push(`built ${formatDate(dataset.built_at)}`);
  return parts.join(" · ");
}

export function formatCell(value: Cell): string {
  if (value === null) return "—";
  if (typeof value === "number") return value.toLocaleString("en-US");
  return value;
}

export function pageLabel(quote: Quote): string | null {
  if (quote.printed_page && quote.pdf_page) {
    return `p. ${quote.printed_page} (PDF p. ${quote.pdf_page})`;
  }
  if (quote.pdf_page) return `PDF p. ${quote.pdf_page}`;
  return null;
}

export const FIGURE_HREF = "#figure-";
export const UNSOURCED_HREF = "#unsourced";

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Turn each number the answer took from a query into a link to that query, and
 * each unsourced number into a marked link that says it is unverified.
 *
 * Done on the markdown text, so the renderer stays a plain markdown renderer.
 * Longest strings first, so "$221,069,148" is linked whole and never split by
 * a shorter figure inside it; a figure already inside a link is left alone.
 */
export function linkFigures(text: string, figures: Figure[], unsourced: string[]): string {
  const targets = new Map<string, string>();
  figures.forEach((figure, index) => {
    for (const shown of figure.in_answer) {
      if (!targets.has(shown)) targets.set(shown, `${FIGURE_HREF}${index}`);
    }
  });
  for (const shown of unsourced) targets.set(shown, UNSOURCED_HREF);
  if (!targets.size) return text;

  const ordered = [...targets.keys()].sort((a, b) => b.length - a.length);
  // Existing links are matched first and kept, so nothing is linked twice.
  const pattern = new RegExp(`(\\[[^\\]]*\\]\\([^)]*\\))|(${ordered.map(escapeRegExp).join("|")})`, "g");
  return text.replace(pattern, (match, link: string | undefined, figure: string | undefined) => {
    if (link || !figure) return match;
    return `[${figure}](${targets.get(figure)})`;
  });
}
