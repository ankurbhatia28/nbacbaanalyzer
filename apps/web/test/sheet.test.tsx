import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CapSheetView } from "@/components/CapSheetView";
import { type CapSheet, describeOver, dollars, marks, percent } from "@/lib/sheet";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** Milwaukee, trimmed: a hard cap, a hold, a qualifying offer, dead cap and an expired exception. */
function sheet(): CapSheet {
  return {
    team: "MIL",
    name: "Milwaukee Bucks",
    season: "2026-2027",
    thresholds: {
      salary_cap: 166_000_000,
      tax_level: 201_690_000,
      first_apron: 210_690_000,
      second_apron: 223_690_000,
    },
    totals: { committed: 150_000_000, cap: 180_000_000, apron: 175_000_000 },
    status: "over_cap",
    ceiling: { level: "first_apron", amount: 210_690_000, room: 35_690_000, triggers: ["Cash Traded"] },
    lines: [
      {
        kind: "contract",
        player: "myles turner",
        name: "Myles Turner",
        amount: 150_000_000,
        counts: { cap: 150_000_000, apron: 150_000_000 },
        label: null,
        later: { "2027-2028": 27_850_077 },
        options: { "2027-2028": "player" },
        source: "fanspo",
      },
      {
        kind: "dead",
        player: "damian lillard",
        name: "Damian Lillard",
        amount: 20_000_000,
        counts: { cap: 20_000_000, apron: 20_000_000 },
        label: null,
        later: {},
        options: {},
        source: "fanspo",
      },
      {
        kind: "hold",
        player: "ousmane dieng",
        name: "Ousmane Dieng",
        amount: 5_000_000,
        counts: { cap: 5_000_000, apron: 0 },
        label: "Bird",
        later: {},
        options: {},
        source: "fanspo",
      },
      {
        kind: "hold",
        player: null,
        name: null,
        amount: 5_000_000,
        counts: { cap: 5_000_000, apron: 5_000_000 },
        label: "Restricted Bird",
        later: {},
        options: {},
        source: "fanspo",
      },
    ],
    later_seasons: ["2027-2028"],
    later_totals: { "2027-2028": 27_850_077 },
    trade_exceptions: [
      {
        amount: 1_000_000,
        available: 1_000_000,
        expires: "2026-07-06",
        expired: true,
        reason: "Old trade",
        source: "spotrac_archive",
        as_of: "2026-02-24",
      },
    ],
    sources: { fanspo: "2026-09-29", bbref_contracts: "2026-09-29", salaryswish: "2026-09-30" },
    warnings: ["Guarantees, trade kickers and no-trade clauses are unknown for every contract."],
    dataset: null,
  };
}

describe("marks", () => {
  it("measures the cap with Team Salary and the tax and aprons with Apron Team Salary", () => {
    const got = Object.fromEntries(marks(sheet()).map((m) => [m.key, m]));
    expect(got.salary_cap!.against).toBe("cap");
    expect(got.salary_cap!.over).toBe(180_000_000 - 166_000_000);
    expect(got.tax_level!.against).toBe("apron");
    expect(got.tax_level!.over).toBe(175_000_000 - 201_690_000);
  });

  it("adds a binding hard cap as its own line", () => {
    const ceiling = marks(sheet()).find((m) => m.key === "ceiling");
    expect(ceiling?.amount).toBe(210_690_000);
    expect(marks({ ...sheet(), ceiling: null }).some((m) => m.key === "ceiling")).toBe(false);
  });

  it("says under or over in words, never a bare signed number", () => {
    expect(describeOver(-4_200_000)).toBe("$4.2M under");
    expect(describeOver(1_100_000)).toBe("$1.1M over");
    expect(describeOver(0)).toBe("exactly at");
  });

  it("keeps a bar inside its track", () => {
    expect(percent(-5, 100)).toBe(0);
    expect(percent(150, 100)).toBe(100);
    expect(dollars(-1_000)).toBe("−$1,000");
  });
});

describe("CapSheetView", () => {
  it("shows each line with what it counts toward, and an unnamed hold as unnamed", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(sheet()))));
    render(<CapSheetView team="MIL" />);
    expect(await screen.findByText("Milwaukee Bucks")).toBeTruthy();
    expect(screen.getByText("Cap only")).toBeTruthy();
    expect(screen.getByText("Unnamed in the source")).toBeTruthy();
    expect(screen.getByText("Over the cap, under the tax")).toBeTruthy();
    expect(screen.getByText(/Hard cap \(at the first apron\)/)).toBeTruthy();
    expect(screen.getByText(/unknown for every contract/)).toBeTruthy();
    expect(screen.getByText("PO")).toBeTruthy();
  });

  it("marks an expired trade exception rather than offering it", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(sheet()))));
    const { container } = render(<CapSheetView team="MIL" />);
    await screen.findByText("Milwaukee Bucks");
    expect(container.querySelector("tr.expired")?.textContent).toMatch(/expired/);
  });

  it("says there is no such team rather than drawing an empty sheet", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 404 })));
    render(<CapSheetView team="XYZ" />);
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText(/There is no cap sheet for XYZ/)).toBeTruthy();
  });
});
