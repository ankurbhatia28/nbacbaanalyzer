import { describe, expect, it } from "vitest";

import { SseParser } from "@/lib/sse";

describe("SseParser", () => {
  it("parses whole events", () => {
    const events = new SseParser().push('event: step\ndata: {"text":"a"}\n\nevent: card\ndata: {}\n\n');
    expect(events).toEqual([
      { event: "step", data: '{"text":"a"}' },
      { event: "card", data: "{}" },
    ]);
  });

  it("holds a partial event until its blank line arrives", () => {
    // Network chunks do not respect event boundaries.
    const parser = new SseParser();
    expect(parser.push("event: tool\nda")).toEqual([]);
    expect(parser.push('ta: {"text":"x"}\n')).toEqual([]);
    expect(parser.push("\n")).toEqual([{ event: "tool", data: '{"text":"x"}' }]);
  });

  it("handles CRLF line endings and ignores comments", () => {
    const events = new SseParser().push(": keep-alive\r\n\r\nevent: step\r\ndata: 1\r\n\r\n");
    expect(events).toEqual([{ event: "step", data: "1" }]);
  });

  it("defaults the event name to message", () => {
    expect(new SseParser().push("data: x\n\n")).toEqual([{ event: "message", data: "x" }]);
  });
});
