/**
 * Permalinks (7.7, D19): the answer card travels in the link.
 *
 * ADR-004 forbids runtime writes, so a link cannot point at a stored answer;
 * re-asking on open would cost money and could give a different answer. So
 * the card itself is compressed into the URL fragment -- which browsers never
 * send to a server -- and opening the link renders exactly what was given.
 *
 * Quote text is the bulk of a card and is the one part that can be recovered
 * deterministically, so it is dropped and re-fetched by passage label. Each
 * dropped quote keeps a hash of its text, and the reopened page compares: if
 * the index was rebuilt and the words changed, the reader is told rather than
 * shown a different quotation under the original citation.
 *
 * Definitions (`define_term`) keep their text inline: they are short, and
 * their citation names the definition rather than a passage label.
 */

import { type AnswerCard, parseCard, type Quote } from "./card";

const VERSION = 1;

interface Payload {
  v: number;
  given_at: string;
  card: AnswerCard;
  /** Hash of each quote's text, by index, for quotes whose text was dropped. */
  hashes: Record<number, string>;
}

export interface Shared {
  card: AnswerCard;
  givenAt: string;
  /** Indices into `card.quotes` whose text must be re-fetched. */
  pending: Map<number, string>;
}

/** FNV-1a, 32-bit. Detects a changed quotation; not a security boundary. */
export function fingerprint(text: string): string {
  let hash = 0x811c9dc5;
  for (const byte of new TextEncoder().encode(text)) {
    hash ^= byte;
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(16).padStart(8, "0");
}

function refetchable(quote: Quote): boolean {
  return quote.tool !== "define_term";
}

async function pipe(bytes: Uint8Array, stream: CompressionStream | DecompressionStream): Promise<Uint8Array> {
  const out = new Response(bytes as BodyInit).body!.pipeThrough(stream);
  return new Uint8Array(await new Response(out).arrayBuffer());
}

function toBase64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function fromBase64Url(text: string): Uint8Array {
  const padded = text.replace(/-/g, "+").replace(/_/g, "/");
  const binary = atob(padded + "=".repeat((4 - (padded.length % 4)) % 4));
  return Uint8Array.from(binary, (c) => c.charCodeAt(0));
}

export async function encode(card: AnswerCard, givenAt: string): Promise<string> {
  const hashes: Record<number, string> = {};
  const quotes = card.quotes.map((q, i) => {
    if (!refetchable(q)) return q;
    hashes[i] = fingerprint(q.text);
    return { ...q, text: "" };
  });
  const payload: Payload = { v: VERSION, given_at: givenAt, card: { ...card, quotes }, hashes };
  const json = new TextEncoder().encode(JSON.stringify(payload));
  return toBase64Url(await pipe(json, new CompressionStream("deflate-raw")));
}

export class BadLink extends Error {}

export async function decode(fragment: string): Promise<Shared> {
  let payload: Payload;
  try {
    const bytes = await pipe(fromBase64Url(fragment), new DecompressionStream("deflate-raw"));
    payload = JSON.parse(new TextDecoder().decode(bytes)) as Payload;
  } catch {
    throw new BadLink("This link is incomplete or damaged. Ask whoever shared it to copy it again.");
  }
  if (payload.v !== VERSION) throw new BadLink(`This link is format ${payload.v}; this page reads ${VERSION}.`);
  const card = parseCard(payload.card);
  const pending = new Map(Object.entries(payload.hashes).map(([i, h]) => [Number(i), h] as const));
  return { card, givenAt: payload.given_at, pending };
}

export interface Restored {
  card: AnswerCard;
  /** Citations whose text could not be recovered or no longer matches. */
  changed: string[];
}

/** Put the quote text back, checking each against the hash taken when shared. */
export function restore(shared: Shared, texts: Record<string, string | null>): Restored {
  const changed: string[] = [];
  const quotes = shared.card.quotes.map((q, i) => {
    const expected = shared.pending.get(i);
    if (expected === undefined) return q;
    const text = texts[q.citation];
    if (typeof text !== "string" || fingerprint(text) !== expected) {
      changed.push(q.citation);
      return { ...q, text: text ?? "" };
    }
    return { ...q, text };
  });
  return { card: { ...shared.card, quotes }, changed };
}

export function permalinkPath(fragment: string): string {
  return `/answer#${fragment}`;
}
