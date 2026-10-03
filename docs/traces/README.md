# Exemplar traces

Five real sessions, captured against the live API and sent to Langfuse, with a
local copy committed here (task 6.10a).

They exist because a hosted trace does not last: Langfuse Cloud Hobby keeps 30
days. A trace worth showing a reader is gone within a month, and the
observability story should not depend on an account being live and in quota.

`exemplars.jsonl` holds one JSON object per session. Regenerate with the
snippet in `docs/build-plan.md` under 6.10a.

| session | events | cost | what it shows |
|---|---|---|---|
| rules lookup | 8 | $0.0326 | resolve → fetch → answer with a verbatim citation |
| refusal (D10 opinion) | 3 | $0.0008 | declined at the router, no tools touched |
| refusal (D6 historical) | 3 | $0.0008 | the other refusal basis |
| data query | 19 | $0.0814 | the expensive shape: 8 model calls, 10 tool calls |
| arithmetic bait | 8 | $0.0309 | states the rule and does **not** finish the sum |

The spread is the point. A refusal costs 3 events and $0.0008; a data question
costs 19 and $0.0814 — a hundredfold. One number per question does not describe
this workload, which is what made the original event estimate wrong (6.13a).

## Shape

Each trace is one agent run, following Langfuse's
[trace guidance](https://langfuse.com/docs/observability/best-practices):

```
AGENT       answer-cba-question      input = the question, output = the answer
  GENERATION  classify-question      model + token usage
  GENERATION  select-provisions
  GENERATION  generate-answer
  RETRIEVER   fetch-provision        a sibling of the generation that asked for it
  RETRIEVER   fetch-provision
  GENERATION  generate-answer        the next round, after the tool results
```

* **The root is an `agent`** and its input and output are the question and the
  answer. Those two fields are what the trace list shows, so they are what a
  reviewer reads first — not a JSON blob of arguments.
* **Tools are `retriever`, not `tool`.** Every tool here looks something up
  without changing state, which is ADR-004 showing through: the database and
  the index are read-only build artifacts.
* **A tool is a sibling of the generation that requested it**, under the agent
  that orchestrates them, rather than dangling at the root.
* **Each model call is its own generation.** Wrapping the loop in one would hide
  what the agent decided after each tool result.
* **Names are verb-first and stable.** They are referenced by evaluators and
  dashboard filters, so they behave like an API — and never contain the model,
  which would break every filter on a model swap.

## Known gap

**Thinking is not captured.** The guidance asks for it on every generation, and
extended thinking is not enabled on these calls, so there is none to record. If
it is turned on, the reasoning blocks should be captured with it.
