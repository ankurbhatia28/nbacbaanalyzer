# Demo script (8.8) — three minutes

Two things the build plan asks the demo to show: **a trade adjudicated with a
citation**, and **a question refused with a reason**. Everything below was run
against the 2026-27 snapshot on 2026-10-07; the verdicts are the engine's and
will not change, but the model's wording differs a little run to run.

## Before recording

- **Wake the API first**: open https://nbacba-api.onrender.com/health and wait
  for `"ok":true` (up to ~30 s). Otherwise the first question shows the wake
  note instead of the demo.
- Run each question once beforehand, so the answer you record is not the
  first on a fresh process (that one costs twice as much and is slower).
  Each question costs $0.01–0.05.
- Browser at ~1280 px wide, zoom 110–125% so the citations read on video.
- Have two tabs open: the chat (`/`) and the trade builder (`/trade`).

## Script

| time | on screen | say |
|---|---|---|
| 0:00 | Home page | "The NBA's collective bargaining agreement is 676 pages of rules that decide which trades are legal. A language model asked 'is this trade legal?' is right most of the time — and its wrong answers look exactly like its right ones. So in this app the model never decides. A rules engine does, and the model only routes the question and restates what the tools found." |
| 0:25 | Ask: *Can the Knicks trade Josh Hart to Phoenix for Devin Booker?* | "A trade. The model hands it to the engine." While it works: "Every number you're about to see comes out of a tool, not the model's memory." |
| 0:45 | The answer: **Not legal** | "Not legal. New York is over the first apron, and taking back $57 million for $21 million fits no exception — and here's the exception it fails, quoted from the Agreement itself, Article VII section 6(j)(1)(iv)." Point at the quote. |
| 1:05 | Scroll to the assumptions | "And it says what it assumed. Trade kickers and no-trade clauses aren't published for these contracts, so the verdict says it rests on that, instead of quietly treating unknown as zero." |
| 1:20 | Trade builder tab: Hart NYK→PHO, Booker PHO→NYK | "The same engine runs the trade builder, with no model at all. Same verdict, same provision, and the numbers: New York goes from the first apron to the second." |
| 1:45 | Back to chat. Ask: *Can the Lakers send Austin Reaves to Boston for Jaylen Brown?* | "It also won't play along with a wrong premise." Answer: Brown is under contract with Philadelphia in this snapshot, not Boston — "so it asks, rather than ruling on a trade that can't happen." |
| 2:05 | Ask: *Should the Nuggets trade Jamal Murray?* | "And a question it won't answer. Whether a trade is *allowed* can be checked. Whether it's *wise* can't — so it declines, says why, and costs a tenth of a cent, because it's refused before any expensive work." |
| 2:25 | Point at "Copy a link to this answer" | "Every answer has a permanent link that reopens exactly what was said, with the quotations re-checked against the Agreement." |
| 2:35 | README's numbers, or say them | "It's measured, not vibed: the engine passed 184 of 184 real trades and caught all 633 illegal variations of them; an adversarial set tries thirty ways to make the model invent numbers; and every answer is traced." |
| 2:55 | Home page | "The rules engine is open source on its own. Link below." |

## If something goes differently

- **The trade answer asks a clarifying question** instead of ruling: re-ask
  with the teams spelled out — *"Can New York trade Josh Hart to the Phoenix
  Suns for Devin Booker straight up?"*
- **The wake note appears**: the API went back to sleep (15 idle minutes).
  Let it finish and re-record the segment.
- **A backup legal trade**, if you want one that passes: *"Can Denver trade
  Jamal Murray to Brooklyn for Michael Porter Jr.?"* — legal, conditionally:
  Brooklyn uses the expanded exception, which hard-caps it at the first apron
  for the rest of the season. Same verdict in the trade builder (pick the
  players from its list; it shows the hard cap in its notes).
