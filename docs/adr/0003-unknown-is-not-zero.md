# ADR-003: Unknown is not zero

**Status:** Accepted · 2026-09-24

## Context

Three contract fields are not available from any source found: trade kickers
(Spotrac renders the column but it is empty league-wide), no-trade clauses, and
cash considerations in trades. See `docs/division-of-labor.md` §4.1.

## Decision

These fields are tri-state: present, absent, or **unknown**. Unknown is never
coerced to zero or false.

Any verdict whose correctness depends on an unknown field must say so:

> Legal, assuming no trade bonus on C.J. McCollum — not verifiable from
> available sources.

## Rationale

Defaulting to zero makes the engine quietly wrong. A trade that is actually
illegal because of a 15% trade kicker would validate clean, with nothing
indicating a guess was made. That is the same invisible failure ADR-001 exists
to prevent, arriving through the data layer instead of the model.

## Consequences

- The engine returns `assumptions` alongside `violations` on every verdict.
- The UI surfaces assumptions next to the verdict, not in a footnote.
- Hand-entered values improve answers incrementally; completeness is not
  required for the system to be useful or honest.
