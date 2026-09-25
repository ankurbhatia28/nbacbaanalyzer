# ADR-002: A structured query DSL, not text-to-SQL

**Status:** Accepted · 2026-09-24

## Context

The system must answer data questions over the league dataset, not just rules
questions — for example, "how many players re-signed using Bird rights in the
past two seasons?"

Three options:

1. **Text-to-SQL.** The model writes SQL against the schema.
2. **Fixed tool catalog.** One parameterized tool per question shape.
3. **Structured query DSL.** The model emits a typed query object; the engine
   validates it against a schema and compiles it to SQL.

## Decision

Option 3.

The model emits a validated object — entity, filters, grouping, aggregation —
and never writes SQL. Invalid queries are rejected by schema validation before
any database access, with the error returned to the model for one bounded retry.

## Rationale

Text-to-SQL is precisely the LLM judgment ADR-001 exists to eliminate. A
generated query that silently joins wrong or misreads a column produces a
plausible number with no error anywhere — the same invisible-failure mode as
letting the model do arithmetic.

A fixed tool catalog is safe but cannot cover open-ended questions, and the
catalog grows without bound as question shapes multiply.

The DSL keeps the surface open-ended while staying verifiable: the schema is
testable, queries are inspectable before execution, and the compiler is
deterministic code with its own unit tests.

## Consequences

- The DSL is a first-class artifact with its own schema, compiler, and tests.
- The UI can show the structured query behind any number it displays.
- Questions the DSL cannot express are refused rather than approximated —
  and each refusal is a candidate for extending the DSL.
- Extending the DSL is a code change with tests, not a prompt change.
