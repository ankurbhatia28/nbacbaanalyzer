import { describe, expect, it } from "vitest";

import { BadLink, decode, encode, fingerprint, restore } from "@/lib/permalink";

import { dataCard } from "./fixtures";

const GIVEN = "2026-10-03T05:00:00.000Z";

function texts(card = dataCard()): Record<string, string> {
  return Object.fromEntries(card.quotes.map((q) => [q.citation, q.text]));
}

describe("permalinks (7.7)", () => {
  it("round-trips a card, with quote text re-fetched and checked", async () => {
    const card = dataCard();
    const shared = await decode(await encode(card, GIVEN));
    expect(shared.givenAt).toBe(GIVEN);
    expect(shared.card.quotes.every((q) => q.text === "")).toBe(true);
    const { card: back, changed } = restore(shared, texts());
    expect(changed).toEqual([]);
    expect(back).toEqual(card);
  });

  it("is URL-safe", async () => {
    expect(await encode(dataCard(), GIVEN)).toMatch(/^[A-Za-z0-9_-]+$/);
  });

  it("says so when a quote's words have changed since the link was made", async () => {
    const shared = await decode(await encode(dataCard(), GIVEN));
    const altered = { ...texts(), "Art. VII §4": "Different words." };
    const { changed } = restore(shared, altered);
    expect(changed).toEqual(["Art. VII §4"]);
  });

  it("says so when a quote can no longer be found", async () => {
    const shared = await decode(await encode(dataCard(), GIVEN));
    const { changed, card } = restore(shared, { ...texts(), "Art. I §1(uuu)": null } as never);
    expect(changed).toEqual(["Art. I §1(uuu)"]);
    expect(card.quotes.find((q) => q.citation === "Art. I §1(uuu)")?.text).toBe("");
  });

  it("keeps a definition's text inline rather than re-fetching it", async () => {
    const card = dataCard();
    card.quotes[0] = { ...card.quotes[0]!, tool: "define_term", text: "“Salary” means..." };
    const shared = await decode(await encode(card, GIVEN));
    expect(shared.card.quotes[0]!.text).toBe("“Salary” means...");
    expect(shared.pending.has(0)).toBe(false);
  });

  it("rejects a damaged link with a sentence, not a stack trace", async () => {
    await expect(decode("not-a-real-link")).rejects.toBeInstanceOf(BadLink);
    const good = await encode(dataCard(), GIVEN);
    await expect(decode(good.slice(0, good.length / 2))).rejects.toBeInstanceOf(BadLink);
  });

  it("fingerprints deterministically", () => {
    expect(fingerprint("abc")).toBe(fingerprint("abc"));
    expect(fingerprint("abc")).not.toBe(fingerprint("abd"));
    expect(fingerprint("")).toBe("811c9dc5");
  });
});
