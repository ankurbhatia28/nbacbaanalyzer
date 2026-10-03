/**
 * The answer card (7.2): verdict, plain English, verbatim quote, citation,
 * assumptions -- plus the query behind every number (7.3) and where and when
 * each figure was observed (7.6).
 *
 * Ordered for a reader who does not know the CBA: what is wrong with this
 * answer first, then the answer, then the words and the data it rests on.
 * Nothing here is computed from the answer text; every field comes from the
 * card, which comes from tool results and the loop's own audit.
 */

import ReactMarkdown, { type Components } from "react-markdown";

import type { AnswerCard as Card, CardWarning, Status } from "@/lib/card";
import { datasetSummary, FIGURE_HREF, linkFigures, UNSOURCED_HREF } from "@/lib/format";
import { seedHref } from "@/lib/trade";

import { FigureView } from "./FigureView";
import { QuoteView } from "./QuoteView";

const STATUS_LABEL: Record<Status, string> = {
  answered: "Answered",
  refused: "Declined",
  clarification: "Needs more detail",
  unavailable: "No answer",
};

function badge(card: Card): { label: string; tone: string; title: string } {
  if (card.status !== "answered") {
    return { label: STATUS_LABEL[card.status], tone: card.status, title: "" };
  }
  return card.verified
    ? {
        label: "Verified",
        tone: "verified",
        title: "Cited, and every figure in it came from a tool result.",
      }
    : {
        label: "Not verified",
        tone: "unverified",
        title: "Read the warnings: part of this answer could not be checked.",
      };
}

const markdown: Components = {
  a({ href, children }) {
    if (href?.startsWith(FIGURE_HREF)) {
      return (
        <a className="figure-link" href={href} title="From a league-data query; see Data below">
          {children}
        </a>
      );
    }
    if (href === UNSOURCED_HREF) {
      return (
        <mark className="unsourced" title="This figure did not come from a tool result">
          {children}
        </mark>
      );
    }
    return (
      <a href={href} target="_blank" rel="noreferrer noopener">
        {children}
      </a>
    );
  },
};

function Warnings({ warnings }: { warnings: CardWarning[] }) {
  if (!warnings.length) return null;
  return (
    <ul className="warnings" role="alert">
      {warnings.map((w) => (
        <li key={w.kind} className={`warning warning-${w.kind}`}>
          {w.message}
          {w.detail.length > 0 && <span className="warning-detail"> {w.detail.join(", ")}</span>}
        </li>
      ))}
    </ul>
  );
}

export function AnswerCard({ card }: { card: Card }) {
  const { label, tone, title } = badge(card);
  const unsourced = card.warnings.find((w) => w.kind === "unsourced_figures")?.detail ?? [];
  const cited = card.quotes.filter((q) => q.cited_in_answer);
  const readOnTheWay = card.quotes.filter((q) => !q.cited_in_answer);
  const used = card.figures.map((f, i) => ({ f, i })).filter(({ f }) => f.in_answer.length);
  const otherQueries = card.figures.map((f, i) => ({ f, i })).filter(({ f }) => !f.in_answer.length);
  // A quote the answer does not name is still evidence when it is the only
  // one; hiding every passage behind a fold would leave nothing to check.
  const shownQuotes = cited.length ? cited : readOnTheWay.slice(0, 1);
  const foldedQuotes = cited.length ? readOnTheWay : readOnTheWay.slice(1);

  return (
    <article className={`card card-${card.status}`}>
      <header className="card-header">
        <span className={`badge badge-${tone}`} title={title}>
          {label}
        </span>
        {card.citations.length > 0 && (
          <span className="citations">{card.citations.slice(0, 3).join(" · ")}</span>
        )}
      </header>

      <Warnings warnings={card.warnings} />

      <div className="answer">
        {card.text.trim() ? (
          <ReactMarkdown components={markdown}>
            {linkFigures(card.text, card.figures, unsourced)}
          </ReactMarkdown>
        ) : (
          <p>No answer was produced for this question.</p>
        )}
      </div>

      {card.status === "answered" && card.refusal_basis && (
        <p className="partial-refusal">
          <strong>Part of this question was declined.</strong> {card.refusal_basis}
        </p>
      )}

      {card.trade && card.trade.players.length > 0 && (
        <p className="to-builder">
          <a href={seedHref(card.trade.players)}>Check this trade in the trade builder →</a>{" "}
          <span className="muted">
            The rules engine runs it against current rosters and shows which rule it breaks.
          </span>
        </p>
      )}

      {card.assumptions.length > 0 && (
        <section className="section">
          <h3>Assumed</h3>
          <ul className="assumptions">
            {card.assumptions.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </section>
      )}

      {shownQuotes.length > 0 && (
        <section className="section">
          <h3>What the Agreement says</h3>
          {shownQuotes.map((q) => (
            <QuoteView key={`${q.citation}:${q.text.length}`} quote={q} />
          ))}
          {foldedQuotes.length > 0 && (
            <details className="fold">
              <summary>
                {foldedQuotes.length} more {foldedQuotes.length === 1 ? "passage" : "passages"} read
                on the way
              </summary>
              {foldedQuotes.map((q) => (
                <QuoteView key={`${q.citation}:${q.text.length}`} quote={q} />
              ))}
            </details>
          )}
        </section>
      )}

      {card.figures.length > 0 && (
        <section className="section">
          <h3>Data</h3>
          {used.map(({ f, i }) => (
            <FigureView key={i} figure={f} index={i} />
          ))}
          {otherQueries.length > 0 && (
            <details className="fold">
              <summary>
                {used.length ? `${otherQueries.length} other` : otherQueries.length}{" "}
                {otherQueries.length === 1 ? "query" : "queries"} run
              </summary>
              {otherQueries.map(({ f, i }) => (
                <FigureView key={i} figure={f} index={i} />
              ))}
            </details>
          )}
        </section>
      )}

      <footer className="card-footer">
        {card.dataset && <span>Data: {datasetSummary(card.dataset)}</span>}
        {card.seconds !== null && <span>{card.seconds.toFixed(1)}s</span>}
        {card.cost_usd !== null && <span>${card.cost_usd.toFixed(3)}</span>}
      </footer>
    </article>
  );
}
