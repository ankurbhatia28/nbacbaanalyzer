import { describe, expect, it } from "vitest";

import { parseCard, SchemaMismatch } from "@/lib/card";
import { datasetSummary, describeObserved, linkFigures, pageLabel, shortSeason } from "@/lib/format";

import { dataCard } from "./fixtures";

describe("provenance in words (7.6)", () => {
  it("labels a scrape date as a scrape date", () => {
    expect(
      describeObserved({ source: "fanspo", rows: 1, basis: "scraped", earliest: "2026-09-29", latest: "2026-09-29" }),
    ).toBe("Fanspo · scraped 29 Sep 2026 · 1 row");
  });

  it("gives a row-dated range as as-of", () => {
    expect(
      describeObserved({
        source: "spotrac_archive",
        rows: 77,
        basis: "row",
        earliest: "2023-11-14",
        latest: "2026-07-18",
      }),
    ).toBe("Spotrac, via the Wayback Machine · as of 14 Nov 2023 – 18 Jul 2026 · 77 rows");
  });

  it("says an undated row's date is unknown rather than borrowing one", () => {
    expect(
      describeObserved({ source: "spotrac_archive", rows: 2, basis: "undated", earliest: null, latest: null }),
    ).toBe("Spotrac, via the Wayback Machine · date unknown · 2 rows");
  });

  it("summarises the dataset with its season, source dates and build date", () => {
    expect(datasetSummary(dataCard().dataset!)).toBe(
      "2026-27 season · sources read 29 Sep 2026 – 30 Sep 2026 · built 3 Oct 2026",
    );
    expect(shortSeason("2026-2027")).toBe("2026-27");
  });
});

describe("linking numbers to their queries (7.3)", () => {
  const { figures } = dataCard();

  it("links a figure the answer took from a query", () => {
    expect(linkFigures("Committed: **$221,069,148**.", figures, [])).toBe(
      "Committed: **[$221,069,148](#figure-1)**.",
    );
  });

  it("marks an unsourced figure", () => {
    expect(linkFigures("It is $31,000,000.", [], ["$31,000,000"])).toBe("It is [$31,000,000](#unsourced).");
  });

  it("does not link inside an existing link, and links the longest match whole", () => {
    const text = "See [$221,069,148](https://x.example) and $221,069,148 and $221,069.";
    const linked = linkFigures(text, [{ ...figures[1]!, in_answer: ["$221,069,148", "$221,069"] }], []);
    expect(linked).toBe(
      "See [$221,069,148](https://x.example) and [$221,069,148](#figure-0) and [$221,069](#figure-0).",
    );
  });

  it("leaves text without figures untouched", () => {
    expect(linkFigures("No numbers (Art. VII §8).", figures, [])).toBe("No numbers (Art. VII §8).");
  });
});

describe("the card contract", () => {
  it("accepts schema 1 and refuses anything else loudly", () => {
    expect(parseCard(dataCard()).status).toBe("answered");
    expect(() => parseCard({ ...dataCard(), schema: 2 })).toThrow(SchemaMismatch);
  });

  it("gives printed and PDF pages", () => {
    expect(pageLabel(dataCard().quotes[1]!)).toBe("p. 11 (PDF p. 35)");
  });
});
