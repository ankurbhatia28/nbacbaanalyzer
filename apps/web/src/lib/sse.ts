/**
 * Server-sent events over a POST response.
 *
 * `EventSource` only does GET, and a question belongs in a request body, so the
 * stream is read with `fetch` and parsed here. Network chunks do not respect
 * event boundaries -- one read can end mid-line -- so the parser buffers until
 * it sees the blank line that ends an event.
 */

export interface ServerEvent {
  event: string;
  data: string;
}

export class SseParser {
  private buffer = "";

  /** Feed a chunk; returns every event it completed. */
  push(chunk: string): ServerEvent[] {
    this.buffer += chunk.replace(/\r\n/g, "\n");
    const out: ServerEvent[] = [];
    let end: number;
    while ((end = this.buffer.indexOf("\n\n")) !== -1) {
      const block = this.buffer.slice(0, end);
      this.buffer = this.buffer.slice(end + 2);
      const parsed = parseBlock(block);
      if (parsed) out.push(parsed);
    }
    return out;
  }
}

function parseBlock(block: string): ServerEvent | null {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith(":")) continue; // comment / keep-alive
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
  }
  return data.length ? { event, data: data.join("\n") } : null;
}
