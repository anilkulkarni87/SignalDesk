# The Metrics That Matter for Production AI Agents

A normal API dashboard can tell you that an endpoint returned `503` in eight
seconds. It cannot tell you whether an agent selected the wrong tool, retrieved
zero documents, spent most of its budget on repeated model rounds, produced a
schema-valid but incorrect answer, or failed before usage was returned.

SignalDesk Commit 16 starts from that gap:

> An agent run is an execution record, not merely an HTTP request.

## Productization creates an operations problem

Before Commit 15, SignalDesk experiments wrote detailed JSON reports. They were
excellent for controlled evaluation, but they were not connected to the live
analyst workflow.

After Commit 15, an analyst could search a customer, run an investigation,
inspect evidence, and authorize an action. That created a new question:

```text
What happened in this exact user run?
```

Answering it requires correlating layers:

```text
HTTP request
model configuration
agent loop
tool execution
retrieval
token usage
cost
final answer
human quality judgment
```

Commit 16 gives those layers one `request_id`.

## Record attempts, including failures

A success-only table creates a comforting fiction. The most important runs for
operations are often the ones that returned no answer.

SignalDesk creates the request identifier before invoking the agent. A
successful run stores the full answer and execution evidence. A failed run
stores its stage, exception type, bounded message, elapsed time, and frozen
model configuration.

The public API still returns a generic error. Operational detail belongs in an
authorized observation, not in a browser error message.

There is an important boundary: authentication, CSRF, and request-schema
rejections are not agent runs because the investigator was never invoked. They
belong in HTTP security telemetry, which is outside this milestone.

## Preserve the dimensions that explain behavior

The observation stores model and prompt version together. Recording only the
model would make a prompt regression invisible; recording only the prompt would
hide a model rollout.

It also stores each tool outcome:

```text
round
tool name
success
error code
latency
returned count
```

Knowledge-search outputs contribute document IDs and retrieval scores. This
makes a weak answer diagnosable:

```text
Was no policy search attempted?
Did the search fail?
Did it return zero documents?
Which documents ranked highest?
Did the final answer cite them?
```

The live dashboard is not a replacement for curated retrieval evaluation. It is
the evidence needed to select the run that should become a regression case.

## Define every denominator

Metrics often become misleading before they become technically incorrect.

SignalDesk defines its operational rates explicitly:

```text
tool failure rate
  = failed tool calls / all tool calls

retrieval failure rate
  = failed or zero-result knowledge calls / all knowledge calls

task success rate
  = COMPLETED answers / all investigation attempts

evaluation pass rate
  = human PASS labels / all human-labeled runs
```

A task that never needed retrieval does not lower the retrieval-failure rate.
A `LIMITED` answer is a returned response but not a successful task. An
unevaluated run does not count as a quality pass.

Those distinctions prevent a green dashboard from hiding missing work.

## Latency needs a distribution

An average can hide the cases that make an interactive product painful.

The dashboard reports p50 and p95 across recorded attempts. p50 describes the
typical run; p95 reveals the slow tail. Both remain separate from the Commit 15
human workflow metric.

```text
agent latency != analyst investigation time
```

The first measures system execution. The second includes reading evidence,
resolving uncertainty, and making a decision.

## Cost and tokens require honesty about unknowns

A successful Responses API result provides input, cached input, output,
reasoning, and total tokens. SignalDesk records all five and the estimated text
cost used by earlier experiments.

If the provider fails before returning usage, the current boundary cannot
recover partial token consumption. The failure record therefore contains zero
recorded tokens and unknown cost.

This makes aggregate cost a lower bound when provider failures exist. Filling
the gap with a guessed number would make the dashboard look complete while
reducing its credibility.

## Runtime success is not answer quality

A model can return valid JSON, complete its tool calls, and still reach the
wrong conclusion.

Commit 16 adds a deliberately separate human label:

```text
NOT_EVALUATED
PASS
FAIL
```

The analyst records a note explaining the judgment. Evaluation updates are
owner-scoped and CSRF-protected.

This is not automated evaluation and it is not ground truth by default. It is a
triage mechanism. Failed labels should be reviewed and promoted into curated
offline eval cases with explicit expected behavior.

## Build the dashboard around debugging

The dashboard starts with aggregate indicators, but the core interaction is
drilling into one run.

The run ledger shows:

```text
status
customer
conclusion or error
latency
tokens
cost
evaluation
```

The selected-run panel shows model, prompt, token breakdown, answer, tool calls,
retrieval documents and scores, errors, and evaluation. This arrangement
supports the actual debugging sequence:

```text
notice a metric change
-> select an outlier
-> inspect execution evidence
-> label quality
-> create a regression case
```

## The FDE lesson

An FDE needs to connect model behavior to customer operations. That requires
more than adding tracing because a framework supports it.

The important questions are:

```text
Which identifier follows the run end to end?
Can failed attempts be inspected?
Which model and prompt produced the answer?
What did retrieval and tools actually return?
Are token and cost values measured or guessed?
What exactly is each metric's denominator?
Can runtime success be separated from answer quality?
Who may inspect and label the run?
```

Commit 16 does not make SignalDesk production-ready. It creates the operational
truth needed to decide what production hardening should address next.
