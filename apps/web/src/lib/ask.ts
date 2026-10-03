/**
 * One question to the API, streamed.
 *
 * Progress is reported as it arrives; the promise resolves with the card. Every
 * way this can fail ends in an `AskError` with a sentence a user can act on,
 * because "something went wrong" and "the server is asleep" call for different
 * responses.
 */

import { type AnswerCard, parseCard } from "./card";
import { SseParser } from "./sse";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Progress {
  kind: "started" | "step" | "tool";
  text: string;
}

export class AskError extends Error {}

export async function ask(
  question: string,
  {
    session,
    signal,
    onProgress,
  }: { session?: string; signal?: AbortSignal; onProgress?: (p: Progress) => void } = {},
): Promise<AnswerCard> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}/ask/stream`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ question, session }),
      signal,
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new AskError(
      `Could not reach the API at ${API_URL}. Is it running? A free-tier server ` +
        "can take about 30 seconds to wake up, so try again in a moment.",
    );
  }
  if (response.status === 422) {
    throw new AskError("That question could not be sent: it is empty or too long.");
  }
  if (!response.ok || !response.body) {
    throw new AskError(`The API answered ${response.status} ${response.statusText}.`);
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  const parser = new SseParser();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    for (const { event, data } of parser.push(value)) {
      const payload = JSON.parse(data) as { text?: string };
      if (event === "card") return parseCard(payload);
      if (event === "error") {
        throw new AskError(`The run failed: ${payload.text ?? "no detail given"}`);
      }
      if (event === "started" || event === "step" || event === "tool") {
        onProgress?.({ kind: event, text: payload.text ?? "" });
      }
      // Anything else -- the closing answer/refused/clarification events,
      // which the card repeats, or an event this page does not know -- is
      // ignored rather than fatal: the card is what has to be understood,
      // and that is version-checked.
    }
  }
  throw new AskError("The answer stream ended before the answer arrived.");
}
