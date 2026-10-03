"use client";

/**
 * Chat as the primary surface (7.1): questions, not forms.
 *
 * One question runs at a time. The API rate-limits per process and a question
 * takes ten to twenty seconds, so queueing a second behind the first would
 * only make both slower to arrive.
 *
 * While a question runs, the steps are shown as they happen (6.9). They are the
 * first place an answer visibly goes wrong -- "searching the Agreement" when you
 * asked for a salary figure says the question was misread.
 */

import { type FormEvent, type KeyboardEvent, useEffect, useRef, useState } from "react";

import { AskError, ask, type Progress } from "@/lib/ask";
import type { AnswerCard as Card } from "@/lib/card";

import { AnswerCard } from "./AnswerCard";
import { ShareLink } from "./ShareLink";

const MAX_CHARS = 500;

export const EXAMPLES = [
  "What is the Standard Traded Player Exception?",
  "How much are the Nuggets committed for in 2026-27?",
  "A team sends out $30,000,000 in salary. How much can it take back?",
  "Should the Nuggets trade Jamal Murray?",
];

interface Turn {
  id: number;
  question: string;
  progress: Progress[];
  card?: Card;
  /** When the card arrived; a permalink says when the answer was given. */
  givenAt?: string;
  error?: string;
}

function Working({ progress, started }: { progress: Progress[]; started: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const steps = progress.filter((p) => p.kind !== "started");
  return (
    <div className="working" aria-live="polite">
      <p className="muted">
        Working… {Math.round((now - started) / 1000)}s
        {steps.length === 0 && " — this usually takes 10 to 20 seconds"}
      </p>
      <ol className="steps">
        {steps.map((p, i) => (
          <li key={i} className={i === steps.length - 1 ? "step step-current" : "step"}>
            {p.text}
          </li>
        ))}
      </ol>
    </div>
  );
}

/**
 * Groups this page's questions into one trace session. `randomUUID` exists only
 * in secure contexts -- https and localhost -- so a phone testing over plain
 * http on the LAN gets a non-cryptographic id instead of a crash.
 */
function sessionId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export function Chat() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState<{ id: number; started: number } | null>(null);
  const [session] = useState(sessionId);
  const abort = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement | null>(null);

  useEffect(() => () => abort.current?.abort(), []);
  useEffect(() => {
    bottom.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [turns.length]);

  function update(id: number, change: (turn: Turn) => Turn) {
    setTurns((all) => all.map((t) => (t.id === id ? change(t) : t)));
  }

  async function submit(question: string) {
    const text = question.trim();
    if (!text || pending || text.length > MAX_CHARS) return;
    const id = Date.now();
    setTurns((all) => [...all, { id, question: text, progress: [] }]);
    setDraft("");
    setPending({ id, started: Date.now() });
    abort.current = new AbortController();
    try {
      const card = await ask(text, {
        session,
        signal: abort.current.signal,
        onProgress: (p) => update(id, (t) => ({ ...t, progress: [...t.progress, p] })),
      });
      update(id, (t) => ({ ...t, card, givenAt: new Date().toISOString() }));
    } catch (error) {
      if (abort.current.signal.aborted) return;
      const message = error instanceof Error ? error.message : String(error);
      update(id, (t) => ({
        ...t,
        error: error instanceof AskError ? message : `Something broke in this page: ${message}`,
      }));
    } finally {
      setPending(null);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void submit(draft);
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submit(draft);
    }
  }

  return (
    <div className="chat">
      {turns.length === 0 && (
        <section className="empty">
          <p>
            Ask about a rule, about league data, or whether a trade is allowed. Every answer cites
            the provision it rests on, or says why it can&apos;t.
          </p>
          <ul className="examples">
            {EXAMPLES.map((q) => (
              <li key={q}>
                <button type="button" onClick={() => void submit(q)} disabled={pending !== null}>
                  {q}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {turns.map((turn) => (
        <section key={turn.id} className="turn">
          <p className="question">{turn.question}</p>
          {turn.card && <AnswerCard card={turn.card} />}
          {turn.card && turn.givenAt && <ShareLink card={turn.card} givenAt={turn.givenAt} />}
          {turn.error && (
            <div className="error" role="alert">
              <p>{turn.error}</p>
              <button type="button" onClick={() => void submit(turn.question)} disabled={pending !== null}>
                Try again
              </button>
            </div>
          )}
          {pending?.id === turn.id && <Working progress={turn.progress} started={pending.started} />}
        </section>
      ))}
      <div ref={bottom} />

      <form className="composer" onSubmit={onSubmit}>
        <label htmlFor="question" className="visually-hidden">
          Your question
        </label>
        <textarea
          id="question"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask about the CBA…"
          rows={2}
          maxLength={MAX_CHARS}
          disabled={pending !== null}
        />
        <div className="composer-row">
          <span className="muted">
            {draft.length > MAX_CHARS - 100 ? `${MAX_CHARS - draft.length} characters left` : ""}
          </span>
          <button type="submit" disabled={pending !== null || !draft.trim()}>
            {pending ? "Working…" : "Ask"}
          </button>
        </div>
      </form>
    </div>
  );
}
