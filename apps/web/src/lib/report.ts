/**
 * "Report this answer": a GitHub issue, pre-filled, for testers.
 *
 * The app stores nothing (ADR-004), so a report has to carry the answer with
 * it. The permalink does (7.7), and an issue holding one can be reopened and
 * checked exactly as given. The issue is opened in the reporter's browser;
 * nothing is sent from here.
 */

export const ISSUES_URL = "https://github.com/ankurbhatia28/nbacbaanalyzer/issues/new";

/**
 * GitHub refuses very long new-issue URLs, and a permalink carries the whole
 * card. Past this length the link is left out and the reporter is asked to
 * paste it, rather than the issue form failing to open.
 */
export const MAX_REPORT_URL = 7000;

const TITLE_CHARS = 80;

export function reportUrl(question: string, permalink: string): string {
  const title =
    "Answer report: " +
    (question.length > TITLE_CHARS ? `${question.slice(0, TITLE_CHARS - 1)}…` : question);
  const build = (link: string) =>
    `${ISSUES_URL}?${new URLSearchParams({
      title,
      body: [
        `**Question:** ${question}`,
        "",
        `**The answer:** ${link}`,
        "",
        "**What is wrong with it** (a wrong figure, the wrong rule, a refusal it should not have made, ...):",
        "",
      ].join("\n"),
    })}`;
  const full = build(permalink);
  return full.length <= MAX_REPORT_URL
    ? full
    : build("(too long to fill in here: use \"Copy a link to this answer\" and paste it)");
}
