# Exemplar traces

Five real sessions, captured against the live API and committed here (task 6.10a).

They exist because a hosted trace does not last: Raindrop's free tier keeps 14
days, Langfuse Cloud's keeps 30. A trace worth showing a reader is gone within a
month, and the observability story should not depend on an account being live
and in quota.

`exemplars.jsonl` holds one JSON object per session. Regenerate with the snippet
in `docs/build-plan.md` under 6.10a.

| session | events | what it shows |
|---|---|---|
| rules lookup | 9 | resolve → fetch → answer with a verbatim citation |
| refusal (D10 opinion) | 3 | declined at the router, no tools touched |
| refusal (D6 historical) | 3 | the other refusal basis |
| data query | 21 | the expensive shape: 8 model calls, 11 tool calls |
| arithmetic bait | 9 | the model states the rule and does **not** finish the sum |

The spread is the point. A refusal costs 3 events and a data question 21, which
is what made the D13 event estimate wrong (6.13a): one number per question does
not describe this workload.

## Reading a span

```json
{"kind": "model_call", "name": "intent", "seconds": 4.7,
 "payload": {"model": "claude-sonnet-5", "input_tokens": 19,
             "cached_tokens": 5133, "system_chars": 16180}}
```

`system_chars` rather than the prompt itself: D4 asks for the system prompt to be
represented, and the intent role's carries 612 provision names. Repeating ~3,000
tokens of vocabulary on every span would make the trace unreadable and, on a
metered backend, expensive.
