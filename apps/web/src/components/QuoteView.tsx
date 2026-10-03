"use client";

import { useState } from "react";

import type { Quote } from "@/lib/card";
import { pageLabel } from "@/lib/format";

/** Long enough to read the operative sentence; the rest is one click away. */
const PREVIEW_CHARS = 600;

/**
 * Provision text exactly as the tool returned it. Clipped for length, never
 * reworded -- the card's promise is the document's words.
 */
export function QuoteView({ quote }: { quote: Quote }) {
  const [open, setOpen] = useState(false);
  const long = quote.text.length > PREVIEW_CHARS;
  const shown = open || !long ? quote.text : `${quote.text.slice(0, PREVIEW_CHARS).trimEnd()}…`;
  const page = pageLabel(quote);

  return (
    <figure className="quote">
      <figcaption>
        <strong>{quote.citation}</strong>
        {page && <span className="muted"> · {page}</span>}
      </figcaption>
      <blockquote>{shown}</blockquote>
      {long && (
        <button type="button" className="link-button" onClick={() => setOpen(!open)}>
          {open ? "Show less" : `Show the full text (${quote.text.length.toLocaleString("en-US")} characters)`}
        </button>
      )}
    </figure>
  );
}
