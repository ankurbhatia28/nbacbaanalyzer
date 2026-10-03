"use client";

/**
 * A permalinked answer (7.7), rebuilt from the URL fragment.
 *
 * Nothing is asked again: the card is the one that was given, and only the
 * quoted text is re-fetched, by exact label, then checked against the hash
 * taken when the link was made.
 */

import { useEffect, useState } from "react";

import { AskError, fetchQuotes } from "@/lib/ask";
import type { AnswerCard as Card } from "@/lib/card";
import { formatDate } from "@/lib/format";
import { BadLink, decode, restore } from "@/lib/permalink";

import { AnswerCard } from "./AnswerCard";

type View =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; card: Card; givenAt: string; changed: string[]; quotesMissing?: string };

export function SharedAnswer() {
  const [view, setView] = useState<View>({ kind: "loading" });

  useEffect(() => {
    const fragment = window.location.hash.slice(1);
    if (!fragment) {
      setView({ kind: "error", message: "This link has no answer in it." });
      return;
    }
    void (async () => {
      let shared;
      try {
        shared = await decode(fragment);
      } catch (error) {
        setView({ kind: "error", message: error instanceof Error ? error.message : String(error) });
        return;
      }
      const labels = [...shared.pending.keys()].map((i) => shared.card.quotes[i]!.citation);
      try {
        const { card, changed } = restore(shared, await fetchQuotes(labels));
        setView({ kind: "ready", card, givenAt: shared.givenAt, changed });
      } catch (error) {
        // The answer is still worth showing without its quotations.
        const { card } = restore(shared, {});
        setView({
          kind: "ready",
          card,
          givenAt: shared.givenAt,
          changed: [],
          quotesMissing: error instanceof AskError ? error.message : String(error),
        });
      }
    })();
  }, []);

  if (view.kind === "loading") return <p className="muted">Opening the shared answer…</p>;
  if (view.kind === "error") {
    return (
      <div className="error" role="alert">
        <p>{view.message}</p>
        <a href="/">Ask a question instead</a>
      </div>
    );
  }
  const { card, givenAt, changed, quotesMissing } = view;
  return (
    <section className="turn">
      <p className="shared-banner muted">
        A shared answer, given on {formatDate(givenAt)}. It is shown as it was given, not asked
        again.
      </p>
      {quotesMissing && (
        <p className="warning" role="alert">
          The quoted provisions could not be loaded: {quotesMissing}
        </p>
      )}
      {changed.length > 0 && (
        <p className="warning" role="alert">
          The Agreement&apos;s text for {changed.join(", ")} no longer matches what this answer
          quoted — the index has been rebuilt since. The citations stand; the words shown are
          today&apos;s.
        </p>
      )}
      <p className="question">{card.question}</p>
      <AnswerCard card={card} />
      <p>
        <a href="/">Ask your own question</a>
      </p>
    </section>
  );
}
