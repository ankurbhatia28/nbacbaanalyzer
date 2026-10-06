"use client";

/** The thirty teams, from the API rather than a hard-coded list the data could outgrow. */

import { useEffect, useState } from "react";

import { AskError } from "@/lib/ask";
import { type Team, fetchTeams } from "@/lib/sheet";

import { WakeNote } from "./WakeNote";

export function TeamPicker({ current, compact = false }: { current?: string; compact?: boolean }) {
  const [teams, setTeams] = useState<Team[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchTeams().then(setTeams, (e: unknown) =>
      setError(e instanceof AskError ? e.message : String(e)),
    );
  }, []);

  if (error && !compact) {
    return (
      <div className="error" role="alert">
        <p>{error}</p>
      </div>
    );
  }
  if (!teams) {
    return compact ? null : (
      <>
        <p className="muted">Loading teams…</p>
        <WakeNote />
      </>
    );
  }
  return (
    <nav aria-label="Teams" className={compact ? "team-picker team-picker-compact" : "team-picker"}>
      {teams.map((t) => (
        <a key={t.key} href={`/cap/${t.key}`} aria-current={t.key === current ? "page" : undefined} title={t.name}>
          {compact ? t.key : t.name}
        </a>
      ))}
    </nav>
  );
}
