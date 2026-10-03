import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AnswerCard } from "@/components/AnswerCard";

import { dataCard } from "./fixtures";

afterEach(cleanup);

describe("AnswerCard", () => {
  it("shows a verified answer with the number linked to its query", () => {
    render(<AnswerCard card={dataCard()} />);
    expect(screen.getByText("Verified")).toBeTruthy();
    const link = screen.getByRole("link", { name: "$221,069,148" });
    expect(link.getAttribute("href")).toBe("#figure-1");
    expect(screen.getByText(/Basketball-Reference contracts · scraped 29 Sep 2026/)).toBeTruthy();
  });

  it("leads with the quote the answer names and folds the rest", () => {
    const { container } = render(<AnswerCard card={dataCard()} />);
    const shown = container.querySelectorAll(".section > .quote figcaption strong");
    expect([...shown].map((n) => n.textContent)).toEqual(["Art. I §1(uuu)"]);
    expect(screen.getByText(/1 more passage read on the way/)).toBeTruthy();
  });

  it("folds the dead-end queries away from the one that supplied the answer", () => {
    render(<AnswerCard card={dataCard()} />);
    expect(screen.getByText("1 other query run")).toBeTruthy();
  });

  it("puts warnings before the answer and does not call it verified", () => {
    const card = dataCard({
      verified: false,
      text: "It is $31,000,000.",
      warnings: [
        {
          kind: "unsourced_figures",
          message: "These figures did not come from a tool result and must not be relied on.",
          detail: ["$31,000,000"],
        },
      ],
    });
    const { container } = render(<AnswerCard card={card} />);
    expect(screen.getByText("Not verified")).toBeTruthy();
    const alert = screen.getByRole("alert");
    const answer = container.querySelector(".answer")!;
    expect(alert.compareDocumentPosition(answer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(container.querySelector("mark.unsourced")?.textContent).toBe("$31,000,000");
  });

  it("shows a refusal as declined, with the decision it rests on", () => {
    const basis = "This asks what a team should do ... (decision D10).";
    render(
      <AnswerCard
        card={dataCard({ status: "refused", text: basis, refusal_basis: basis, quotes: [], figures: [], citations: [] })}
      />,
    );
    expect(screen.getByText("Declined")).toBeTruthy();
    expect(screen.getByText(/decision D10/)).toBeTruthy();
    expect(screen.queryByText(/Part of this question was declined/)).toBeNull();
  });

  it("says when part of an answered question was declined", () => {
    render(<AnswerCard card={dataCard({ refusal_basis: "Opinion is out of scope (decision D10)." })} />);
    expect(screen.getByText(/Part of this question was declined/)).toBeTruthy();
  });

  it("says so when there is no answer at all", () => {
    render(<AnswerCard card={dataCard({ status: "unavailable", text: "", verified: false })} />);
    expect(screen.getByText("No answer")).toBeTruthy();
    expect(screen.getByText(/No answer was produced/)).toBeTruthy();
  });
});
