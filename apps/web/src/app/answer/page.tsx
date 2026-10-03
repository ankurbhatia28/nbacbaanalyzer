import type { Metadata } from "next";

import { SharedAnswer } from "@/components/SharedAnswer";

export const metadata: Metadata = {
  title: "Shared answer · CBA Analyzer",
  // The answer lives in the URL fragment, which crawlers never see.
  robots: { index: false },
};

export default function AnswerPage() {
  return (
    <main className="page">
      <header className="masthead">
        <h1>
          <a href="/" className="home-link">
            CBA Analyzer
          </a>
        </h1>
      </header>
      <SharedAnswer />
    </main>
  );
}
