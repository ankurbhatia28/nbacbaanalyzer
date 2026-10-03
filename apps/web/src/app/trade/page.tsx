import type { Metadata } from "next";

import { TradeBuilder } from "@/components/TradeBuilder";

export const metadata: Metadata = { title: "Trade builder · CBA Analyzer" };

export default function TradePage() {
  return (
    <main className="page page-wide">
      <header className="masthead">
        <h1>
          <a href="/" className="home-link">
            CBA Analyzer
          </a>
        </h1>
        <p className="muted">
          Build a trade between current rosters. The rules engine checks it as it changes, and says
          which rule a failing trade breaks and what a passing one rests on.
        </p>
      </header>
      <TradeBuilder />
    </main>
  );
}
