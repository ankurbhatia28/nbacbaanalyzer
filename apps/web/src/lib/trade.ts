/**
 * The trade builder (7.4): its state, its URL, and the API calls behind it.
 *
 * The verdict comes from `POST /trade`, which runs the rules engine -- this
 * file decides nothing about legality. What it does decide is the URL: a trade
 * lives in the query string, so any trade can be linked, and a chat answer can
 * open the builder with the players its question named.
 */

import { API_URL, AskError } from "./ask";
import type { Dataset } from "./card";

export interface Move {
  player: string;
  from: string;
  to: string;
}

export interface BuilderState {
  teams: string[];
  moves: Move[];
}

export const MAX_TEAMS = 4;

/**
 * `?teams=DEN,DAL&m=DEN>DAL:jamal murray`. The player key goes last because it
 * is the one part that may contain anything; team keys never contain ">" or ":".
 */
export function encodeState(state: BuilderState): string {
  const params = new URLSearchParams();
  const teams = state.teams.filter(Boolean);
  if (teams.length) params.set("teams", teams.join(","));
  for (const m of state.moves) params.append("m", `${m.from}>${m.to}:${m.player}`);
  return params.toString();
}

export function decodeState(query: URLSearchParams): BuilderState {
  const teams = (query.get("teams") ?? "")
    .split(",")
    .map((t) => t.trim().toUpperCase())
    .filter(Boolean)
    .slice(0, MAX_TEAMS);
  const moves: Move[] = [];
  for (const raw of query.getAll("m")) {
    const match = /^([A-Za-z]{2,4})>([A-Za-z]{2,4}):(.+)$/.exec(raw);
    if (!match) continue;
    const move = { from: match[1]!.toUpperCase(), to: match[2]!.toUpperCase(), player: match[3]! };
    if (teams.includes(move.from) && teams.includes(move.to) && move.from !== move.to) {
      moves.push(move);
    }
  }
  return { teams, moves };
}

export interface Seeded {
  player: string;
  name: string;
  team: string | null;
}

/**
 * A chat answer names players, not directions. With two teams the direction
 * is not a guess -- each player goes to the other team -- so the trade is
 * filled in. With three or more it would be, so the teams are set and the
 * directions are left to the reader.
 */
export function stateFromSeed(seeded: Seeded[]): { state: BuilderState; unplaced: Seeded[] } {
  const placed = seeded.filter((s) => s.team);
  const teams = [...new Set(placed.map((s) => s.team!))].slice(0, MAX_TEAMS);
  const unplaced = seeded.filter((s) => !s.team);
  if (teams.length === 1) teams.push("");
  if (teams.length !== 2) return { state: { teams, moves: [] }, unplaced };
  const [a, b] = teams as [string, string];
  const moves = b
    ? placed.map((s) => ({ player: s.player, from: s.team!, to: s.team === a ? b : a }))
    : [];
  return { state: { teams, moves }, unplaced };
}

export interface TradePlayer {
  player: string;
  name: string;
  amount: number;
  no_trade_clause: "unknown" | boolean;
}

export interface Position {
  cap: number;
  apron: number;
  status: "room" | "over_cap" | "taxpayer" | "first_apron" | "second_apron";
  standard_contracts: number | null;
  ceiling: { level: string; amount: number } | null;
}

export interface TradeViolation {
  code: string;
  detail: string;
  subject: string | null;
  citation: string;
  title: string;
}

export interface Side {
  team: string;
  name: string;
  sends: TradePlayer[];
  receives: TradePlayer[];
  outgoing: number;
  incoming: number;
  before: Position;
  after: Position;
  violations: TradeViolation[];
}

export interface Provision {
  quoted: string | null;
  text: string | null;
  pdf_page: number | null;
  printed_page: number | null;
}

export interface TradeVerdict {
  legal: boolean;
  conditional: boolean;
  season: string;
  as_of: string;
  sides: Side[];
  assumptions: { subject: string; field: string; assumed: unknown; reason: string }[];
  notes: string[];
  unsourced: string[];
  provisions: Record<string, Provision>;
  dataset: Dataset | null;
}

/** The engine's notes, without the fixed list of checks, which is shown on its own. */
export function splitNotes(notes: string[]): { checked: string | null; perTeam: string[] } {
  const checked = notes.find((n) => n.startsWith("checked: ")) ?? null;
  return {
    checked: checked ? checked.slice("checked: ".length) : null,
    perTeam: notes.filter((n) => n !== checked),
  };
}

/** Whether a team can send this move, given the teams in the trade. */
export function destinations(teams: string[], from: string): string[] {
  return teams.filter((t) => t && t !== from);
}

export async function checkTrade(moves: Move[], signal?: AbortSignal): Promise<TradeVerdict> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}/trade`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ moves }),
      signal,
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new AskError(
      `Could not reach the API at ${API_URL}. A free-tier server can take about 30 seconds ` +
        "to wake up, so try again in a moment.",
    );
  }
  if (response.status === 422 || response.status === 404) {
    const body = (await response.json().catch(() => ({}))) as { detail?: unknown };
    throw new AskError(
      typeof body.detail === "string" ? body.detail : "That trade could not be checked as given.",
    );
  }
  if (!response.ok) throw new AskError(`The API answered ${response.status} ${response.statusText}.`);
  return (await response.json()) as TradeVerdict;
}

export async function fetchSeed(players: string[]): Promise<Seeded[]> {
  const query = new URLSearchParams(players.map((p) => ["key", p]));
  let response: Response;
  try {
    response = await fetch(`${API_URL}/players?${query.toString()}`);
  } catch {
    throw new AskError(`Could not reach the API at ${API_URL} to look up the players.`);
  }
  if (!response.ok) throw new AskError(`The API answered ${response.status} ${response.statusText}.`);
  return ((await response.json()) as { players: Seeded[] }).players;
}

/** `/trade?player=...&player=...` -- what a chat answer links to. */
export function seedHref(players: string[]): string {
  return `/trade?${new URLSearchParams(players.map((p) => ["player", p])).toString()}`;
}
