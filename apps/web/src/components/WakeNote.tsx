"use client";

/**
 * Why a request is slow when the API is asleep (8.6).
 *
 * The API runs on Render's free tier (D21), which spins down after about
 * fifteen minutes idle. Render holds a request while the server wakes rather
 * than failing it, so the "could not reach the API" message never shows: the
 * page just waits, and a chat question that usually takes 10 to 20 seconds
 * sits at "Working… 35s" with nothing said. This says it.
 *
 * Mounted only while something is waiting on the API, so unmounting resets it.
 */

import { useEffect, useState } from "react";

/** Long enough that a warm server has always answered (or, in chat, started). */
export const WAKE_AFTER_MS = 8000;

export const WAKE_TEXT =
  "Still waiting for the server. It sleeps after a quiet spell and takes about 30 seconds " +
  "to wake up; once it is awake, requests are quick again.";

export function WakeNote({ after = WAKE_AFTER_MS }: { after?: number }) {
  const [show, setShow] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setShow(true), after);
    return () => clearTimeout(timer);
  }, [after]);
  return show ? (
    <p className="muted small" role="status">
      {WAKE_TEXT}
    </p>
  ) : null;
}
