"use client";

/**
 * The trade builder (7.4). Pick the teams, choose who goes where, and the
 * engine's verdict updates as the trade changes.
 *
 * The verdict is the engine's, from `POST /trade`. What it rests on is shown
 * with it, not under it: the assumptions (trade kickers no source carries),
 * the checks that run on no data, and the list of checks that ran at all --
 * so "legal" is never read as "nothing else could be wrong".
 */

import { useEffect, useMemo, useRef, useState } from "react";

import { AskError } from "@/lib/ask";
import { datasetSummary, formatDate, shortSeason } from "@/lib/format";
import { type CapSheet, STATUS_LABEL, dollars, fetchSheet, fetchTeams, millions, type Team } from "@/lib/sheet";
import {
  type BuilderState,
  MAX_TEAMS,
  type Move,
  type Seeded,
  type Side,
  type TradeVerdict,
  checkTrade,
  decodeState,
  destinations,
  encodeState,
  fetchSeed,
  splitNotes,
  stateFromSeed,
} from "@/lib/trade";

import { WakeNote } from "./WakeNote";

type Verdict =
  | { kind: "idle" }
  | { kind: "checking" }
  | { kind: "error"; message: string }
  | { kind: "ready"; verdict: TradeVerdict };

export function TradeBuilder() {
  const [teams, setTeams] = useState<Team[]>([]);
  const [state, setState] = useState<BuilderState>({ teams: ["", ""], moves: [] });
  const [loaded, setLoaded] = useState(false);
  const [unplaced, setUnplaced] = useState<Seeded[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [sheets, setSheets] = useState<Record<string, CapSheet | "loading" | string>>({});
  const [verdict, setVerdict] = useState<Verdict>({ kind: "idle" });
  const inflight = useRef<AbortController | null>(null);

  // -- the URL is the state ----------------------------------------------
  useEffect(() => {
    fetchTeams().then(setTeams, (e: unknown) => setLoadError(message(e)));
    const query = new URLSearchParams(window.location.search);
    const seed = query.getAll("player");
    if (seed.length && !query.has("teams")) {
      fetchSeed(seed).then(
        (found) => {
          const { state: seeded, unplaced: missing } = stateFromSeed(found);
          setState(seeded.teams.length >= 2 ? seeded : { ...seeded, teams: [...seeded.teams, ""] });
          setUnplaced(missing);
          setLoaded(true);
        },
        (e: unknown) => {
          setLoadError(message(e));
          setLoaded(true);
        },
      );
      return;
    }
    const decoded = decodeState(query);
    while (decoded.teams.length < 2) decoded.teams.push("");
    setState(decoded);
    setLoaded(true);
  }, []);

  useEffect(() => {
    if (!loaded) return;
    const query = encodeState(state);
    window.history.replaceState(null, "", query ? `/trade?${query}` : "/trade");
  }, [state, loaded]);

  // -- rosters -----------------------------------------------------------
  useEffect(() => {
    for (const key of state.teams) {
      if (!key || sheets[key]) continue;
      setSheets((s) => ({ ...s, [key]: "loading" }));
      fetchSheet(key).then(
        (sheet) => setSheets((s) => ({ ...s, [key]: sheet })),
        (e: unknown) => setSheets((s) => ({ ...s, [key]: message(e) })),
      );
    }
  }, [state.teams, sheets]);

  // -- the live verdict --------------------------------------------------
  const movesKey = JSON.stringify(state.moves);
  useEffect(() => {
    inflight.current?.abort();
    if (!loaded || state.moves.length === 0) {
      setVerdict({ kind: "idle" });
      return;
    }
    const controller = new AbortController();
    inflight.current = controller;
    setVerdict({ kind: "checking" });
    const timer = setTimeout(() => {
      checkTrade(state.moves, controller.signal).then(
        (v) => setVerdict({ kind: "ready", verdict: v }),
        (e: unknown) => {
          if (!controller.signal.aborted) setVerdict({ kind: "error", message: message(e) });
        },
      );
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
    // movesKey stands for state.moves, compared by value rather than identity.
  }, [movesKey, loaded]);

  // -- edits -------------------------------------------------------------
  function setTeam(index: number, key: string) {
    setState((s) => {
      const old = s.teams[index];
      const next = [...s.teams];
      next[index] = key;
      return {
        teams: next,
        moves: s.moves.filter((m) => m.from !== old && m.to !== old),
      };
    });
  }

  function addTeam() {
    setState((s) => (s.teams.length < MAX_TEAMS ? { ...s, teams: [...s.teams, ""] } : s));
  }

  function removeTeam(index: number) {
    setState((s) => {
      const gone = s.teams[index];
      return {
        teams: s.teams.filter((_, i) => i !== index),
        moves: s.moves.filter((m) => m.from !== gone && m.to !== gone),
      };
    });
  }

  function route(player: string, from: string, to: string) {
    setState((s) => {
      const rest = s.moves.filter((m) => m.player !== player);
      return { ...s, moves: to ? [...rest, { player, from, to }] : rest };
    });
  }

  const chosen = state.teams.filter(Boolean);

  return (
    <div className="builder">
      {loadError && (
        <div className="error" role="alert">
          <p>{loadError}</p>
        </div>
      )}
      {unplaced.length > 0 && (
        <p className="warning">
          Not under contract with any team this season, so left out:{" "}
          {unplaced.map((u) => u.name).join(", ")}.
        </p>
      )}

      <div className="builder-teams">
        {state.teams.map((key, index) => (
          <TeamColumn
            key={index}
            index={index}
            team={key}
            teams={teams}
            taken={state.teams}
            sheet={key ? sheets[key] : undefined}
            moves={state.moves}
            destinations={destinations(state.teams, key)}
            onTeam={(k) => setTeam(index, k)}
            onRoute={route}
            onRemove={state.teams.length > 2 ? () => removeTeam(index) : undefined}
          />
        ))}
      </div>
      {state.teams.length < MAX_TEAMS && (
        <button type="button" className="link-button" onClick={addTeam}>
          + Add a team
        </button>
      )}

      <section className="verdict" aria-live="polite">
        <VerdictView verdict={verdict} hasTeams={chosen.length >= 2} />
      </section>
    </div>
  );
}

function message(e: unknown): string {
  return e instanceof AskError ? e.message : String(e);
}

function TeamColumn(props: {
  index: number;
  team: string;
  teams: Team[];
  taken: string[];
  sheet: CapSheet | "loading" | string | undefined;
  moves: Move[];
  destinations: string[];
  onTeam: (key: string) => void;
  onRoute: (player: string, from: string, to: string) => void;
  onRemove?: () => void;
}) {
  const { team, sheet } = props;
  const contracts = useMemo(
    () =>
      typeof sheet === "object"
        ? sheet.lines.filter((l) => l.kind === "contract" && l.amount > 0 && l.player)
        : [],
    [sheet],
  );
  return (
    <div className="builder-team">
      <div className="builder-team-head">
        <label>
          <span className="visually-hidden">Team {props.index + 1}</span>
          <select value={team} onChange={(e) => props.onTeam(e.target.value)}>
            <option value="">Choose a team…</option>
            {props.teams.map((t) => (
              <option key={t.key} value={t.key} disabled={t.key !== team && props.taken.includes(t.key)}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
        {props.onRemove && (
          <button type="button" className="link-button" onClick={props.onRemove} aria-label="Remove this team">
            Remove
          </button>
        )}
      </div>
      {team && typeof sheet === "object" && (
        <p className="muted small">
          {STATUS_LABEL[sheet.status]} · Apron Team Salary{" "}
          <span className="num">{millions(sheet.totals.apron)}</span> ·{" "}
          <a href={`/cap/${team}`}>cap sheet</a>
        </p>
      )}
      {sheet === "loading" && <p className="muted small">Loading the roster…</p>}
      {typeof sheet === "string" && sheet !== "loading" && <p className="warning">{sheet}</p>}
      {contracts.length > 0 && (
        <table className="builder-roster">
          <tbody>
            {contracts.map((line) => {
              const move = props.moves.find((m) => m.player === line.player);
              return (
                <tr key={line.player} className={move ? "moving" : undefined}>
                  <td>{line.name ?? line.player}</td>
                  <td className="num">{millions(line.amount)}</td>
                  <td>
                    <select
                      aria-label={`Where ${line.name ?? line.player} goes`}
                      value={move?.to ?? ""}
                      onChange={(e) => props.onRoute(line.player!, team, e.target.value)}
                      disabled={props.destinations.length === 0}
                    >
                      <option value="">Keeps</option>
                      {props.destinations.map((d) => (
                        <option key={d} value={d}>
                          → {d}
                        </option>
                      ))}
                    </select>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

function VerdictView({ verdict, hasTeams }: { verdict: Verdict; hasTeams: boolean }) {
  if (verdict.kind === "idle") {
    return (
      <p className="muted">
        {hasTeams
          ? "Choose who goes where, and the rules engine checks the trade as it changes."
          : "Choose two teams to start."}
      </p>
    );
  }
  if (verdict.kind === "checking") {
    return (
      <>
        <p className="muted">Checking the trade…</p>
        <WakeNote />
      </>
    );
  }
  if (verdict.kind === "error") {
    return (
      <div className="error" role="alert">
        <p>{verdict.message}</p>
      </div>
    );
  }
  const v = verdict.verdict;
  const { checked, perTeam } = splitNotes(v.notes);
  return (
    <article className="card">
      <header className="card-header">
        <span className={`badge ${v.legal ? "badge-verified" : "badge-unavailable"}`}>
          {v.legal ? "Legal" : "Not legal"}
        </span>
        {v.conditional && <span className="badge">Rests on assumptions</span>}
        <span className="muted small">
          {shortSeason(v.season)} · as of {formatDate(v.as_of)}
        </span>
      </header>

      <div className="trade-sides">
        {v.sides.map((s) => (
          <SideView key={s.team} side={s} />
        ))}
      </div>

      {v.sides.some((s) => s.violations.length) && (
        <section className="section">
          <h3>Why not</h3>
          {v.sides.flatMap((s) =>
            s.violations.map((x, i) => {
              const text = v.provisions[x.citation];
              return (
                <div key={`${s.team}-${i}`} className="violation">
                  <p>
                    <strong>{s.team}</strong>
                    {x.subject ? ` (${x.subject})` : ""}: {x.detail}.{" "}
                    <span className="muted">{x.citation}</span>
                  </p>
                  {text?.text && (
                    <details className="fold">
                      <summary>
                        {text.quoted === x.citation
                          ? `Read ${x.citation}`
                          : `Read ${text.quoted}, which contains ${x.citation}`}
                        {text.printed_page ? ` · p. ${text.printed_page}` : ""}
                      </summary>
                      <blockquote className="quote">{text.text}</blockquote>
                    </details>
                  )}
                </div>
              );
            }),
          )}
        </section>
      )}

      {perTeam.length > 0 && (
        <section className="section">
          <h3>What it costs</h3>
          <ul className="assumptions">
            {perTeam.map((n) => (
              <li key={n}>{n}.</li>
            ))}
          </ul>
        </section>
      )}

      <section className="section">
        <h3>What this rests on</h3>
        <ul className="assumptions">
          {v.unsourced.map((u) => (
            <li key={u}>{u}</li>
          ))}
        </ul>
        {checked && <p className="muted small">Checked: {checked}. Nothing outside this list was checked.</p>}
      </section>

      {v.dataset && <footer className="card-footer muted">Dataset: {datasetSummary(v.dataset)}</footer>}
    </article>
  );
}

function SideView({ side }: { side: Side }) {
  const names = (list: Side["sends"]) =>
    list.length ? list.map((p) => `${p.name} (${millions(p.amount)})`).join(", ") : "nothing";
  const changed = side.before.status !== side.after.status;
  return (
    <div className={`trade-side${side.violations.length ? " trade-side-failing" : ""}`}>
      <h4>{side.name}</h4>
      <p>
        Sends {names(side.sends)}. Receives {names(side.receives)}.
      </p>
      <p className="muted small">
        Apron Team Salary{" "}
        <span className="num">
          {dollars(side.before.apron)} → {dollars(side.after.apron)}
        </span>{" "}
        ·{" "}
        {changed
          ? `${STATUS_LABEL[side.before.status]} → ${STATUS_LABEL[side.after.status]}`
          : STATUS_LABEL[side.after.status]}
      </p>
    </div>
  );
}
