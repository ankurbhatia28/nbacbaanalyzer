import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AnswerCard } from "@/components/AnswerCard";
import { TradeBuilder } from "@/components/TradeBuilder";
import {
  type TradeVerdict,
  decodeState,
  encodeState,
  seedHref,
  splitNotes,
  stateFromSeed,
} from "@/lib/trade";

import { dataCard } from "./fixtures";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("the trade lives in the URL", () => {
  it("round-trips, player keys and all", () => {
    const state = {
      teams: ["DEN", "DAL"],
      moves: [
        { player: "jamal murray", from: "DEN", to: "DAL" },
        { player: "kel'el ware", from: "DAL", to: "DEN" },
      ],
    };
    expect(decodeState(new URLSearchParams(encodeState(state)))).toEqual(state);
  });

  it("drops a move involving a team not in the trade rather than inventing one", () => {
    const got = decodeState(new URLSearchParams("teams=DEN,DAL&m=DEN>BOS:jamal murray&m=junk"));
    expect(got).toEqual({ teams: ["DEN", "DAL"], moves: [] });
  });
});

describe("seeding from a chat answer", () => {
  it("fills in directions when two teams make them certain", () => {
    const { state } = stateFromSeed([
      { player: "jamal murray", name: "Jamal Murray", team: "DEN" },
      { player: "kyrie irving", name: "Kyrie Irving", team: "DAL" },
    ]);
    expect(state.moves).toEqual([
      { player: "jamal murray", from: "DEN", to: "DAL" },
      { player: "kyrie irving", from: "DAL", to: "DEN" },
    ]);
  });

  it("sets three teams but leaves the directions to the reader", () => {
    const { state } = stateFromSeed([
      { player: "a", name: "A", team: "DEN" },
      { player: "b", name: "B", team: "DAL" },
      { player: "c", name: "C", team: "BOS" },
    ]);
    expect(state).toEqual({ teams: ["DEN", "DAL", "BOS"], moves: [] });
  });

  it("leaves a second team open when only one is named, and reports who has no team", () => {
    const { state, unplaced } = stateFromSeed([
      { player: "a", name: "A", team: "DEN" },
      { player: "z", name: "Z", team: null },
    ]);
    expect(state).toEqual({ teams: ["DEN", ""], moves: [] });
    expect(unplaced.map((u) => u.name)).toEqual(["Z"]);
  });

  it("links one parameter per player, so a name may hold a comma", () => {
    expect(seedHref(["a, jr", "b"])).toBe("/trade?player=a%2C+jr&player=b");
  });

  it("is offered on an answer that carries players, and only then", () => {
    const { container } = render(
      <AnswerCard card={{ ...dataCard(), trade: { players: ["jamal murray"] } }} />,
    );
    expect(container.querySelector('a[href="/trade?player=jamal+murray"]')).toBeTruthy();
    cleanup();
    render(<AnswerCard card={dataCard()} />);
    expect(screen.queryByText(/trade builder/)).toBeNull();
  });
});

it("separates the list of checks from what the trade costs each team", () => {
  expect(splitNotes(["checked: a, b", "DAL: matched by the expanded exception"])).toEqual({
    checked: "a, b",
    perTeam: ["DAL: matched by the expanded exception"],
  });
});

const VERDICT: TradeVerdict = {
  legal: false,
  conditional: true,
  season: "2026-2027",
  as_of: "2026-10-03",
  sides: [
    {
      team: "DEN",
      name: "Denver Nuggets",
      sends: [{ player: "jamal murray", name: "Jamal Murray", amount: 50_105_628, no_trade_clause: "unknown" }],
      receives: [{ player: "kyrie irving", name: "Kyrie Irving", amount: 59_304_326, no_trade_clause: "unknown" }],
      outgoing: 50_105_628,
      incoming: 59_304_326,
      before: { cap: 1, apron: 217_245_280, status: "first_apron", standard_contracts: 14, ceiling: null },
      after: { cap: 1, apron: 226_443_978, status: "second_apron", standard_contracts: 14, ceiling: null },
      violations: [
        {
          code: "apron_transaction_barred",
          detail: "takes back $59,304,326 against $50,105,628 sent, which needs the expanded exception",
          subject: null,
          citation: "Art. VII §2(e)(2)(i)(A)",
          title: "t",
        },
      ],
    },
  ],
  assumptions: [],
  notes: ["checked: salary matching, hard cap ceilings"],
  unsourced: ["No source carries no-trade clauses or trade kickers; kickers are assumed absent."],
  provisions: {
    "Art. VII §2(e)(2)(i)(A)": {
      quoted: "Art. VII §2(e)(2)(i)",
      text: "A Team may not engage in a transaction set forth in the Transaction Restrictions Table…",
      pdf_page: 212,
      printed_page: 211,
    },
  },
  dataset: null,
};

function api(url: string): Response {
  if (url.endsWith("/teams")) {
    return Response.json({ teams: [{ key: "DEN", name: "Denver Nuggets" }, { key: "DAL", name: "Dallas Mavericks" }] });
  }
  if (url.includes("/teams/")) return new Response("{}", { status: 503 });
  if (url.endsWith("/trade")) return Response.json(VERDICT);
  return new Response("{}", { status: 404 });
}

it("checks a trade from the URL and says which rule it breaks, quoting the passage that holds it", async () => {
  window.history.replaceState(null, "", "/trade?teams=DEN,DAL&m=DEN>DAL:jamal murray");
  const fetchMock = vi.fn(async (url: string) => api(url));
  vi.stubGlobal("fetch", fetchMock);
  render(<TradeBuilder />);
  expect(await screen.findByText("Not legal")).toBeTruthy();
  expect(screen.getByText("Rests on assumptions")).toBeTruthy();
  expect(screen.getByText(/First apron → Over the second apron|Over the first apron → Over the second apron/)).toBeTruthy();
  expect(screen.getByText(/Read Art. VII §2\(e\)\(2\)\(i\), which contains Art. VII §2\(e\)\(2\)\(i\)\(A\)/)).toBeTruthy();
  expect(screen.getByText(/Nothing outside this list was checked/)).toBeTruthy();
  const trade = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/trade"));
  expect(JSON.parse(String((trade as unknown as [string, RequestInit])[1].body))).toEqual({
    moves: [{ player: "jamal murray", from: "DEN", to: "DAL" }],
  });
});
