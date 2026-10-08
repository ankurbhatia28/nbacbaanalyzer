# Trying the CBA Analyzer

Thanks for testing. **https://nbacbaanalyzer.vercel.app**

Ask about the NBA's 2023 Collective Bargaining Agreement — its rules, team
payrolls and contracts, or whether a trade is allowed. Every answer cites the
provision it rests on, or says why it can't answer. The most useful thing you
can find is an answer that is **wrong but sounds right**.

## Before you start

- **The first request can take ~30 seconds.** The server sleeps after 15 quiet
  minutes and the page says so while it wakes. After that, a question takes
  10–30 seconds, because each one is looked up rather than recalled.
- **The league data is a snapshot from late September 2026**, for the 2026-27
  season. Rosters are whatever they were then, which may not be what you
  remember. If you name a player on the wrong team, it should tell you rather
  than answer anyway.
- **Guarantees, trade kickers and no-trade clauses are unknown for every
  contract** — no source the app reads carries them. A trade verdict says what
  it assumed about them. That is deliberate: an unknown is never treated as
  zero.

## Things to try

- A trade: *"Can the Knicks trade Josh Hart to Phoenix for Devin Booker?"* —
  then build the same deal in the [trade builder](https://nbacbaanalyzer.vercel.app/trade)
  and check the two agree.
- A team's limits: *"If I wanted to trade Embiid, what are the limitations the
  76ers have?"*
- League data: *"Which team has the most cap space?"*, *"Who won MVP in
  2023-24?"*, *"Which players hold a player option for 2027-28?"*
- A rule: *"What does the second apron restrict?"*, *"What is the Gilbert
  Arenas provision?"*
- A [team's cap sheet](https://nbacbaanalyzer.vercel.app/cap), with every figure
  dated to where it came from.

Then try to break it: ask it to skip the lookup and just estimate, ask about a
rule in casual words, ask a trade with three teams, ask something it should
decline.

## What it declines, on purpose

- **Past seasons**, except All-NBA, Defensive Player of the Year and MVP from
  2020-21 on. "What was the cap in 2019-20?" is declined: only the current
  snapshot is held.
- **Opinions**: "Should the Nuggets trade Murray?" — whether a trade is
  *allowed* can be checked; whether it is *wise* cannot.
- **Anything off topic**, including games, scores and player statistics.

A decline with a stated reason is the app working. A decline of something it
*should* answer is a bug worth reporting.

## Reporting a problem

Under each answer, **"Report a problem with this answer"** opens a GitHub
issue with the question and a link to the exact answer already filled in;
just say what is wrong. (It needs a GitHub account. Without one, use **"Copy
a link to this answer"** and send the link with a note.)

Most useful: a wrong figure, a wrong rule or citation, a verdict you believe
is wrong (and why), a refusal it should not have made, or an answer that
states something without a citation.

## Privacy

Questions are logged to improve the app. When the main model is unavailable a
free third-party model may answer, and its provider may keep what it is sent.
Don't type anything private.

Not affiliated with the NBA or the NBPA. Not legal advice.
