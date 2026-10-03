import type { Metadata } from "next";

import { TeamPicker } from "@/components/TeamPicker";

export const metadata: Metadata = { title: "Cap sheets · CBA Analyzer" };

export default function CapIndex() {
  return (
    <main className="page">
      <header className="masthead">
        <h1>
          <a href="/" className="home-link">
            CBA Analyzer
          </a>
        </h1>
        <p className="muted">
          Each team's books for the current season: every contract, cap hold and dead-cap line, and
          where the totals sit against the cap, the tax and both aprons.
        </p>
      </header>
      <TeamPicker />
    </main>
  );
}
