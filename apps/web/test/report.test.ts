import { describe, expect, it } from "vitest";

import { ISSUES_URL, MAX_REPORT_URL, reportUrl } from "@/lib/report";

const LINK = "https://nbacbaanalyzer.vercel.app/answer#abc_DEF-123";

function fields(url: string) {
  const params = new URL(url).searchParams;
  return { title: params.get("title") ?? "", body: params.get("body") ?? "" };
}

describe("report this answer", () => {
  it("opens a new issue carrying the question and the answer's permalink", () => {
    const url = reportUrl("Who won MVP in 2023-24?", LINK);
    expect(url.startsWith(`${ISSUES_URL}?`)).toBe(true);
    const { title, body } = fields(url);
    expect(title).toBe("Answer report: Who won MVP in 2023-24?");
    expect(body).toContain("**Question:** Who won MVP in 2023-24?");
    expect(body).toContain(LINK);
  });

  it("shortens a long question in the title but keeps it whole in the body", () => {
    const question = "Is it legal ".repeat(20);
    const { title, body } = fields(reportUrl(question, LINK));
    expect(title.length).toBeLessThanOrEqual("Answer report: ".length + 80);
    expect(title.endsWith("…")).toBe(true);
    expect(body).toContain(question);
  });

  it("leaves out a permalink too long for GitHub rather than fail to open", () => {
    const long = `${LINK}${"x".repeat(MAX_REPORT_URL)}`;
    const url = reportUrl("Is this trade legal?", long);
    expect(url.length).toBeLessThanOrEqual(MAX_REPORT_URL);
    expect(fields(url).body).not.toContain(long);
    expect(fields(url).body).toContain("Copy a link to this answer");
  });
});
