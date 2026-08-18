# From Agent Loops to Stateful AI Workflows With LangGraph

An agent loop already contains a workflow, even when it is written as a `for`
loop.

The loop has a request. It accumulates model messages and tool results. It
branches when the model requests a function. It stops when the model returns a
final answer. It fails when an API call, tool, or validation step raises. Those
are workflow concepts expressed through local variables and control flow.

SignalDesk Commit 10 built that primitive loop directly. Commit 11 asks a more
specific question:

> What becomes easier to control and measure when the same loop is represented
> as an explicit state graph?

The goal is not to make the model smarter. The model, prompt, tools, cases, and
rubric remain fixed.

## Start from the control experiment

The accepted Commit 10 system uses:

```text
model              gpt-5.6-luna
reasoning           none
prompt              commit10_v4_campaign_evidence_budget
tools               six read-only CDP functions
cases               50 frozen customers
answer              strict InvestigationAnswer schema
evaluation          Commit 10 V4 rubric
```

Only orchestration changes. The baseline is a manual Responses API loop. The
candidate is a LangGraph `StateGraph`.

Without this boundary, a better score could come from a prompt edit, new tool,
changed case, different model, or weaker evaluator. Framework adoption would
be mixed with behavior change.

## Make hidden state explicit

The manual loop keeps important values in local variables:

```text
validated request
model input transcript
pending function calls
tool traces
model rounds and token totals
final structured answer
```

The graph moves those values into a typed state object. Each node reads the
current state and returns a partial update.

This produces named transitions:

```text
START
  -> interpret_request
  -> resolve_customer
  -> investigation_router
       -> profile
       -> events
       -> knowledge
       -> reason_about_case
       -> recommend_action
  -> approval_required
  -> finish
  -> END
```

The model still proposes a tool. The application maps each allowed tool to a
route:

```text
profile    customer profile, metrics, campaign readiness
events     digital events and purchase history
knowledge  current approved policy search
```

This distinction matters. The graph does not give the model more authority. It
makes the application's response to a model decision visible.

## A node is a failure boundary

In a plain loop, recovery often means rerunning the function and reconstructing
whatever state was lost. In a checkpointed graph, each completed step can be a
restart point.

The Commit 11 graph uses an in-memory checkpointer and a unique thread ID. If
the reasoning node fails, the latest snapshot still contains the validated
request, resolved customer, transcript, traces, and the next node to execute.
Resuming the thread retries that node without repeating earlier work.

The distinction can be stated from first principles:

```text
retry       repeat an operation
checkpoint  remember a completed boundary
resume      continue from a remembered boundary
```

These are related but not interchangeable. A retry policy can handle a
temporary API failure inside one node. A checkpoint can recover the workflow
after the node exits unsuccessfully and control returns to the caller.

## Persistence has levels

Using a checkpointer does not automatically make a system durable.

Commit 11 uses `InMemorySaver`. It supports state history and resume while the
Python process remains alive. It does not survive a process restart and should
not be presented as production persistence.

A durable workflow would need a persistent checkpointer, thread lifecycle,
retention rules, encryption and access controls, schema migration, replay
semantics, and operational monitoring. Learning the state contract first keeps
those infrastructure choices from hiding the orchestration lesson.

## Draw the action edge without granting authority

The roadmap includes recommendation, approval, and action execution. Real
human approval and consequential tools belong to the next milestone.

Commit 11 therefore makes the boundary explicit but inert:

```text
recommendation    ANALYSIS_ONLY
approval_required false
action_executed   false
```

The action node raises a safety error if reached.

This is a useful design rule: a graph can represent a future capability before
the runtime is permitted to perform it. Architecture and authority do not have
to arrive together.

## Test workflow mechanics without model variance

The first evaluation isolates orchestration. Each of the 50 accepted Commit 10
runs is converted into two workflow scenarios:

```text
standard replay
checkpoint-recovery replay with one injected reasoning-node failure
```

The replay supplies the accepted function calls and final structured answer,
while the graph executes the real deterministic CDP tools. This creates 100
scenarios without new model API calls.

The result is:

```text
completion                 100%
correct routing            100%
tool-count agreement       100%
rubric task completion     100%
recovery                   100%
average tool calls         2.22
failed executions          0
actions executed           0
```

Completed runs created between 14 and 18 checkpoints.

This result supports a narrow claim: given fixed model decisions, the graph
routes, executes, checkpoints, resumes, and terminates correctly.

It does not support the claim that LangGraph improved answer quality. The
accepted answer was replayed, so answer quality was held constant by design.

## Measure live parity separately

The second evaluation ran the model again over the same 50 frozen customers.
It compared the LangGraph candidate with the stored manual-loop baseline on:

```text
task completion and every rubric component
per-case improvements and regressions
correct routing
tool calls
latency
input and output tokens
estimated cost
```

That comparison answered a different question: did the orchestration change
preserve external behavior during a new stochastic run?

The live result should not be mixed into the deterministic recovery number.
One measures graph mechanics under fixed decisions. The other measures
end-to-end behavior with model variance.

The answer was yes for this measured run:

| Metric | Manual loop | LangGraph |
|---|---:|---:|
| API success | 100% | 100% |
| Correct tools | 100% | 100% |
| Correct arguments | 100% | 100% |
| Unnecessary-tools empty | 98% | 100% |
| Correct conclusions | 100% | 100% |
| Required evidence | 100% | 100% |
| Policy citations evidenced | 100% | 100% |
| Task completion | 100% | 100% |
| Correct graph routing | not applicable | 100% |

There were no per-case task regressions, routing failures, approval-required
paths, or executed actions.

## Compare operational behavior without inventing causality

The two runs also produced different operational measurements:

| Measurement | Manual loop | LangGraph |
|---|---:|---:|
| Mean latency | 6.0616s | 5.4044s |
| p50 latency | 5.4742s | 5.0890s |
| p95 latency | 9.2174s | 7.7938s |
| Tool calls | 111 | 110 |
| API requests | 106 | 103 |
| Input tokens | 302,870 | 293,566 |
| Output tokens | 22,966 | 22,730 |
| Estimated cost | $0.236846 | $0.233834 |

The LangGraph run wrote 826 checkpoints, averaging 16.52 per task. Forty-seven
tasks completed in two model rounds and three used three rounds. No API retry
or failed tool execution occurred.

The manual-loop run contained one duplicate metrics call. It did not recur in
the LangGraph run. Two engagement cases also completed in one fewer model
round.

It would be incorrect to conclude that LangGraph caused these improvements.
The model is probabilistic, and this comparison contains one run per treatment.
The framework changed how state and transitions were represented, not the
instructions that decide which tools to call. The defensible conclusion is
behavioral parity without measured regression, not automatic efficiency from a
graph.

## Keep the remaining limitations visible

The policy metrics still measure provenance more strongly than semantic
entailment. Seventeen of 20 cited excerpts use the same generic uncertainty and
escalation passage. The documents are current, approved, retrieved, and cited
with exact text, but most excerpts are not the most specific support for the
business rule.

The deterministic benchmark injected a failure and proved checkpoint resume.
The live run had no failures, so it did not exercise live recovery. The
in-memory checkpointer also loses state when the process stops.

Finally, the 50 tasks are a development regression suite. They are not a
holdout, and one stochastic run does not establish a production reliability
rate. There is still no write-capable tool, human approval step, or production
action.

## What I learned

1. A loop is already a state machine; a graph makes that state machine
   inspectable.
2. Frameworks organize control flow. They do not replace prompts, tool
   contracts, schemas, or evaluation.
3. Named routes let routing correctness be measured independently from final
   answer correctness.
4. Retry, checkpoint, and resume solve different parts of failure recovery.
5. In-memory checkpoints demonstrate semantics but do not provide durable
   production persistence.
6. Future action nodes can be modeled before the system receives write
   authority.
7. Deterministic replay and live model comparison support different claims and
   should remain separate experiments.
8. A framework comparison should freeze model behavior inputs and treat
   operational differences as observations until repeated runs support a causal
   claim.
9. Checkpoint counts and transition traces make orchestration observable, but
   durable persistence and human approval remain separate capabilities.

The useful reason to adopt LangGraph is not that an agent now looks like a
diagram. It is that state, transitions, recovery points, and safety gates become
contracts that can be inspected and tested.

For SignalDesk, LangGraph earned adoption because the explicit workflow
preserved all accepted behavior, routed every tool correctly, recovered from
injected failure, and kept the future action boundary closed. It did not earn
adoption by claiming to make the model smarter.
