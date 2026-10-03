/**
 * A team's cap sheet (7.5), as `GET /teams/{key}/sheet` sends it.
 *
 * Mirrors `packages/data/src/nbadata/sheet.py`, which is the definition. The
 * helpers below are pure, so what a reader is told about a team's position --
 * which line it is over, by how much, measured against which total -- is
 * tested without rendering anything.
 */

import { API_URL, AskError } from "./ask";
import type { Dataset } from "./card";

export type LineKind = "contract" | "hold" | "dead";

export interface Line {
  kind: LineKind;
  player: string | null;
  name: string | null;
  amount: number;
  counts: { cap: number; apron: number };
  label: string | null;
  later: Record<string, number>;
  options: Record<string, string>;
  source: string;
}

export interface HeldException {
  amount: number;
  available: number | null;
  expires: string | null;
  expired: boolean | null;
  reason: string | null;
  source: string;
  as_of: string | null;
}

export type Status = "room" | "over_cap" | "taxpayer" | "first_apron" | "second_apron";

export interface Thresholds {
  salary_cap: number;
  tax_level: number;
  first_apron: number;
  second_apron: number;
}

export interface CapSheet {
  team: string;
  name: string;
  season: string;
  thresholds: Thresholds;
  totals: { committed: number; cap: number; apron: number };
  status: Status;
  ceiling: { level: string; amount: number; room: number | null; triggers: string[] } | null;
  lines: Line[];
  later_seasons: string[];
  later_totals: Record<string, number>;
  trade_exceptions: HeldException[];
  sources: Record<string, string>;
  warnings: string[];
  dataset: Dataset | null;
}

export interface Team {
  key: string;
  name: string;
}

export const STATUS_LABEL: Record<Status, string> = {
  room: "Under the cap",
  over_cap: "Over the cap, under the tax",
  taxpayer: "Taxpayer, under the first apron",
  first_apron: "Over the first apron",
  second_apron: "Over the second apron",
};

export const KIND_LABEL: Record<LineKind, string> = {
  contract: "Contract",
  hold: "Cap hold",
  dead: "Dead cap",
};

export const OPTION_LABEL: Record<string, string> = {
  player: "PO",
  team: "TO",
  eto: "ETO",
};

/** "$166,000,000". Whole dollars: the sheet is where a reader checks a sum. */
export function dollars(amount: number): string {
  const sign = amount < 0 ? "−" : "";
  return `${sign}$${Math.abs(amount).toLocaleString("en-US")}`;
}

/** "$166.0M", for labels where the full figure would not fit. */
export function millions(amount: number): string {
  const sign = amount < 0 ? "−" : "";
  return `${sign}$${(Math.abs(amount) / 1_000_000).toFixed(1)}M`;
}

export interface Mark {
  key: keyof Thresholds | "ceiling";
  label: string;
  short: string;
  amount: number;
  /** Which total this line is measured against -- the point the sheet exists to make. */
  against: "cap" | "apron";
  /** That total minus the line: negative is room below it, positive is over. */
  over: number;
}

/**
 * The four thresholds, each against the total that the Agreement measures it
 * with. Room is a cap question, asked of Team Salary with holds included; the
 * tax and the aprons are asked of Apron Team Salary (Art. VII §2(e)(1)). A
 * binding hard cap is added as a fifth line, because it is the one a team
 * cannot cross at all.
 */
export function marks(sheet: CapSheet): Mark[] {
  const t = sheet.thresholds;
  const { cap, apron } = sheet.totals;
  const out: Mark[] = [
    { key: "salary_cap", label: "Salary cap", short: "Cap", amount: t.salary_cap, against: "cap", over: cap - t.salary_cap },
    { key: "tax_level", label: "Tax level", short: "Tax", amount: t.tax_level, against: "apron", over: apron - t.tax_level },
    { key: "first_apron", label: "First apron", short: "1st", amount: t.first_apron, against: "apron", over: apron - t.first_apron },
    { key: "second_apron", label: "Second apron", short: "2nd", amount: t.second_apron, against: "apron", over: apron - t.second_apron },
  ];
  if (sheet.ceiling) {
    const level = sheet.ceiling.level === "first_apron" ? "first" : "second";
    out.push({
      key: "ceiling",
      label: `Hard cap (at the ${level} apron)`,
      short: "Hard cap",
      amount: sheet.ceiling.amount,
      against: "apron",
      over: apron - sheet.ceiling.amount,
    });
  }
  return out;
}

/** "$4.2M under" / "$1.1M over" / "exactly at". */
export function describeOver(over: number): string {
  if (over === 0) return "exactly at";
  return over < 0 ? `${millions(-over)} under` : `${millions(over)} over`;
}

/**
 * The bar's scale: zero to a little past the highest of the totals and the
 * second apron. From zero, not from a truncated floor, so the lengths are
 * honest; the thresholds are close together, which is itself the fact.
 */
export function scaleMax(sheet: CapSheet): number {
  return Math.max(sheet.totals.cap, sheet.totals.apron, sheet.thresholds.second_apron) * 1.05;
}

export function percent(amount: number, max: number): number {
  return Math.min(100, Math.max(0, (amount / max) * 100));
}

export function lineName(line: Line): string {
  if (line.name) return line.name;
  return line.player ?? "Unnamed in the source";
}

async function getJson(path: string, what: string): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`);
  } catch {
    throw new AskError(
      `Could not reach the API at ${API_URL} to load ${what}. A free-tier server can take ` +
        "about 30 seconds to wake up, so try again in a moment.",
    );
  }
  if (response.status === 404) throw new AskError(`There is no ${what}.`);
  if (!response.ok) throw new AskError(`The API answered ${response.status} ${response.statusText}.`);
  return response.json();
}

export async function fetchTeams(): Promise<Team[]> {
  const body = (await getJson("/teams", "the list of teams")) as { teams: Team[] };
  return body.teams;
}

export async function fetchSheet(team: string): Promise<CapSheet> {
  return (await getJson(`/teams/${encodeURIComponent(team)}/sheet`, `cap sheet for ${team}`)) as CapSheet;
}
