# SignalDesk Commit 13 - Comparing Agent Runtimes

Commit 13 implements one small approval workflow twice:

```text
LangGraph
vs
OpenAI Agents SDK
```

The goal is framework selection, not framework loyalty.

## Question

> When behavior and domain contracts are fixed, which runtime better matches
> SignalDesk's current workflow shape?

Commit 12's full five-action LangGraph workflow remains unchanged. The Agents
SDK candidate implements one representative `ISSUE_COUPON` path with the same
immutable action proposal, human decision, action ledger, synthetic event, and
idempotency key.

## Fixed comparison contract

```text
fixed                              changed
-----                              -------
20 frozen coupon cases             orchestration runtime
10 approve / 10 reject             checkpoint representation
5 post-commit failures             approval primitive
ActionProposal schema              routing representation
ApprovalDecision schema
ActionStore SQLite ledger
exact-payload validation
audit expectations
duplicate-action rule
```

The Agents SDK production path defaults to:

```text
model       gpt-5.6-luna
reasoning   none
```

The deterministic benchmark replaces the network model with a fixed SDK
`Model` implementation. It emits the frozen tool call and final response through
the real `Runner`. This isolates orchestration, produces no API cost, and avoids
mistaking model variance for framework behavior.

## Two implementations

### LangGraph

```text
typed graph state
-> named nodes and conditional edges
-> SQLite checkpointer
-> interrupt(payload)
-> Command(resume=decision)
-> application action node
```

### OpenAI Agents SDK

```text
Agent + function tool
-> model emits tool call
-> tool declares needs_approval=True
-> RunResult.interruptions
-> serialized RunState JSON
-> state.approve() / state.reject()
-> Runner resume
```

The SDK owns tool-call interruption state. Application code still validates the
arguments against the immutable proposal, records the human decision, and uses
the Commit 12 idempotent ledger for the side effect.

## Measured result

Both runtimes executed all 20 cases:

| Metric | LangGraph | OpenAI Agents SDK |
|---|---:|---:|
| Approval gated | 100% | 100% |
| Correct outcome | 100% | 100% |
| Fully audited | 100% | 100% |
| Recovery | 100% | 100% |
| Duplicate-action rate | 0% | 0% |
| Mean local runtime | 26.6771 ms | 19.4219 ms |
| p95 local runtime | 35.2724 ms | 26.6900 ms |
| Mean pending-state artifact | 28,672 bytes | 8,285 bytes |
| Adapter source lines | 224 | 270 |

There were 40 runtime executions, 40 deterministic model replay calls, zero
external model API calls, and no parity failures.

The timing and size results do not establish framework superiority:

- model latency is excluded and would dominate a live request;
- 20 local runs are not a production performance study;
- LangGraph's value is a SQLite file allocation, while the SDK value is JSON
  payload length;
- source lines depend on repository integration choices and are not a quality
  score;
- the existing LangGraph module supports all five action types while the SDK
  candidate deliberately supports one.

Behavioral parity is the defensible result.

## Framework comparison

| Concern | LangGraph | OpenAI Agents SDK |
|---|---|---|
| State | Typed shared graph state with automatic checkpoints | Serializable `RunState`; application chooses storage |
| Routing | Explicit nodes and conditional edges | Implicit model/tool runner loop |
| Tool calls | Application routes to action node | SDK-native function tools |
| HITL | Application-defined interrupt payload | Native tool `needs_approval` and interruptions |
| Tracing | State history and named transitions | Built-in agent, model, and tool spans |
| Testability | Node methods and snapshots | Injectable custom `Model` and serialized state |
| Persistence | Checkpointer abstraction | JSON state plus application persistence |

The SDK documentation describes approval interruptions and durable
`RunState` serialization in its
[human-in-the-loop guide](https://openai.github.io/openai-agents-python/human_in_the_loop/).

## Dependency finding

`openai-agents==0.18.3` requires `openai>=2.45,<3`. Installing it resolved the
shared OpenAI client from `3.2.0` to `2.54.0`. All SignalDesk tests still pass,
but framework adoption changed a foundational dependency. That must be reviewed
in a real customer repository rather than treated as installation trivia.

## Decision

Retain LangGraph for the current SignalDesk workflow.

SignalDesk has explicit investigation routes, durable long-running approval,
recovery nodes, and application-owned action semantics. Named state transitions
make those control boundaries easy to inspect and test.

Prefer the OpenAI Agents SDK when the primary abstraction is a model/tool loop
and native tool approvals, tracing, sessions, or handoffs provide more value
than an explicit domain graph. The SDK candidate passed the same safety
contract, so it is a viable alternative rather than a rejected technology.

## Install and reproduce

```bash
python -m pip install -r requirements-commit13.txt
python -m unittest discover -s tests -v
python -m evals.commit13.make_cases
python -m evals.commit13.runner
```

The report is:

```text
evals/commit13/reports/runtime_comparison.json
```

## Live SDK demonstration

Export `OPENAI_API_KEY` in the same terminal and run:

```bash
python run_agents_sdk_demo.py
```

The live path uses `gpt-5.6-luna` with reasoning `none`. It should produce an
SDK-native interruption before asking for approval. The live result is a
demonstration, not part of the deterministic comparison report.

## What this milestone teaches

1. Framework APIs are implementations of architectural requirements.
2. Framework comparisons need a fixed behavioral contract.
3. Native approval does not replace application authorization or idempotency.
4. A serializable run state is not a persistence strategy until the application
   chooses where and how to store it.
5. Faster local orchestration does not predict end-to-end model latency.
6. Dependency constraints are part of framework selection.
7. The right question is not which framework is best; it is which runtime fits
   this workflow and operating environment.
