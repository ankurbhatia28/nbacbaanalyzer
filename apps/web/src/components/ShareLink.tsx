"use client";

import { useState } from "react";

import type { AnswerCard } from "@/lib/card";
import { encode, permalinkPath } from "@/lib/permalink";
import { reportUrl } from "@/lib/report";

/**
 * A link to exactly this answer (7.7), and a way to report it. Built in the browser from the card; no
 * request is made and nothing is stored. Where the clipboard is unavailable
 * (plain http, an old browser) the link is shown for copying by hand.
 */
export function ShareLink({ card, givenAt }: { card: AnswerCard; givenAt: string }) {
  const [state, setState] = useState<"idle" | "copied" | { manual: string }>("idle");

  async function share() {
    const url = `${window.location.origin}${permalinkPath(await encode(card, givenAt))}`;
    try {
      await navigator.clipboard.writeText(url);
      setState("copied");
      setTimeout(() => setState("idle"), 2500);
    } catch {
      setState({ manual: url });
    }
  }

  async function report() {
    // Opened before the await, or a popup blocker treats it as unrequested.
    const tab = window.open("", "_blank");
    const url = `${window.location.origin}${permalinkPath(await encode(card, givenAt))}`;
    const target = reportUrl(card.question, url);
    if (tab) {
      tab.opener = null;
      tab.location.href = target;
    } else {
      window.location.href = target;
    }
  }

  return (
    <div className="share">
      <button type="button" className="link-button" onClick={() => void share()}>
        {state === "copied" ? "Link copied" : "Copy a link to this answer"}
      </button>
      {" · "}
      <button type="button" className="link-button" onClick={() => void report()}>
        Report a problem with this answer
      </button>
      {typeof state === "object" && (
        <input
          className="share-manual"
          readOnly
          value={state.manual}
          aria-label="Link to this answer"
          onFocus={(e) => e.currentTarget.select()}
          autoFocus
        />
      )}
    </div>
  );
}
