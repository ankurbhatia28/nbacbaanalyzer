# ADR-001: The model does not compute, interpret, or recall

**Status:** Accepted · 2026-09-24

## Context

The NBA Collective Bargaining Agreement is a ~676-page legal instrument
governing a deterministic arithmetic system. Questions about it have right
answers that can be checked.

A language model asked "is this trade legal?" will answer confidently and be
right most of the time. Most of the time is the worst possible accuracy: wrong
answers are indistinguishable from right ones, and the failure is silent.

## Decision

The model translates, routes, and explains. It never decides.

Specifically, the model may **not**:

1. **Compute.** No salary matching, no apron arithmetic, no cap totals. All
   numbers come from the rules engine.
2. **Interpret rules.** It never decides which CBA provision applies. The engine
   emits a violation code; a static table maps that code to an Article and
   Section; retrieval fetches that provision verbatim.
3. **Recall facts.** No player salaries, contract terms, or roster facts from
   memory. Every fact enters through a tool result.

The model **does**: parse natural language into structured intent, choose which
tool to call, and compose prose that restates tool output.

## Consequences

- Every rule in `packages/engine` is written from the CBA text with an Article
  and Section citation attached, never from memory or secondary sources.
- `packages/engine` imports no LLM client. This is enforced by lint.
- Data the sources do not carry is modelled as `unknown`, never defaulted.
  A verdict touching an unknown says so. See ADR-003.
- Questions the tools cannot answer are refused, not guessed.
- An adversarial eval suite exists specifically to catch the model doing
  arithmetic or asserting rules without a tool call.

## Why this is the whole project

Any competent developer can wire a chat interface to a PDF. The engineering
claim here is the split: retrieval where it belongs, computation where it
belongs, and a measurable boundary between them.
