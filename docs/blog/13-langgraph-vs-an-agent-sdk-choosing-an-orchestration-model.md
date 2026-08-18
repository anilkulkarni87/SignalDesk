# LangGraph vs an Agent SDK: Choosing an Orchestration Model

Learning one framework can create the illusion that its abstractions are the
architecture. They are not.

An approval workflow needs state, routing, an authority boundary, durable
interruption, audit history, and idempotent execution. LangGraph and the OpenAI
Agents SDK provide different ways to implement those requirements.

SignalDesk Commit 13 implements one fixed coupon-approval workflow with both
runtimes. The goal is not to name a universal winner. It is to practice making
a defensible framework decision.

## Freeze behavior before comparing frameworks

A framework comparison is invalid if the candidate also changes the prompt,
model behavior, tools, cases, schema, and evaluator.

The experiment freezes 20 Commit 12 coupon cases:

```text
10 approved
10 rejected
5 approved cases fail after the event commits
```

Both runtimes use the same:

```text
ActionProposal
ApprovalDecision
ActionStore
synthetic event format
audit sequence
immutable action ID
duplicate-action rule
```

Only orchestration changes.

## LangGraph makes the domain graph explicit

The LangGraph implementation names each control boundary:

```text
validate proposal
record proposal
record approval request
await approval
record decision
execute action
finish
```

A SQLite checkpointer stores typed graph state after each node. Human review is
an `interrupt`, and the application resumes with a `Command` containing the
decision.

This representation is useful when the business process itself is the primary
thing to understand. A snapshot can say exactly which domain node is next.

## The Agents SDK makes the model/tool loop explicit

The SDK candidate defines an `issue_coupon` function tool with
`needs_approval=True`. The runner calls the model, receives a tool call, and
returns an interruption instead of executing the tool.

The application converts the result to `RunState`, serializes it as JSON,
reconstructs it later, records the human decision, calls `state.approve()` or
`state.reject()`, and resumes the original agent.

The OpenAI Agents SDK documents this interruption and serialization pattern in
its [human-in-the-loop guide](https://openai.github.io/openai-agents-python/human_in_the_loop/).

This representation is useful when the model/tool loop is the primary
abstraction. Approval belongs directly to the sensitive tool call.

## Native approval is not the entire permission system

The SDK can pause a tool, but application code still has to answer:

```text
Does this tool call match the exact proposal the human sees?
Who is the reviewer?
Where is the decision audited?
What happens after a crash?
How is duplicate execution prevented?
```

SignalDesk validates every interrupted tool argument against the immutable
proposal before presenting it. A test changes the model-proposed discount from
10% to 50%; the application rejects the interruption and writes no event.

Both implementations reuse the Commit 12 action ledger. The immutable action
ID remains the idempotency key. Framework-native HITL complements application
authorization; it does not replace it.

## Deterministic replay isolates orchestration

The Agents SDK accepts a custom `Model`. The benchmark uses a deterministic
implementation that emits the frozen tool call and final response through the
real `Runner`.

That choice produces:

```text
40 runtime executions
40 deterministic model replay calls
0 external model API calls
```

It tests interruption, serialization, reconstruction, approve/reject, tool
execution, and recovery without model variance or API cost.

The SDK adapter still defaults to `gpt-5.6-luna` with reasoning `none` for the
separate live demonstration. The deterministic benchmark does not claim to
measure model quality.

## Result

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

Both runtimes satisfy the frozen permission contract.

## Do not overread the operational numbers

The SDK candidate was faster in this local deterministic run and wrote a
smaller pending-state artifact. Neither result establishes superiority.

There is no network model latency. Twenty cases are not a load test. The state
sizes compare a SQLite file allocation with JSON payload length. The
implementations also expose different abstractions.

The reliable conclusion is parity. The timing and size values describe this
experiment, not production performance.

## Framework adoption changed a shared dependency

The pinned `openai-agents==0.18.3` package requires `openai>=2.45,<3`.
Installation changed SignalDesk's resolved OpenAI client from `3.2.0` to
`2.54.0`.

All repository tests still passed. That does not make the constraint
irrelevant. In a customer codebase, a framework can force coordinated upgrades
or downgrades across unrelated services. Dependency compatibility belongs in
the architecture decision.

## Decision for SignalDesk

SignalDesk retains LangGraph.

Its current workflow has explicit investigation routes, durable approval,
recovery boundaries, and application-owned action semantics. Named nodes and
checkpoint snapshots make those business transitions directly inspectable.

The Agents SDK remains a valid option. I would prefer it for a smaller
model-centric tool loop where native approvals, sessions, handoffs, and tracing
are more valuable than an explicit domain graph.

The decision is contextual:

```text
explicit long-running business state machine -> LangGraph fits naturally
model-centric tool and handoff loop           -> Agents SDK fits naturally
```

## What I learned

1. State, routing, approval, and idempotency exist independently of framework
   syntax.
2. Changing only the runtime is necessary for a credible comparison.
3. Native tool approval still needs application payload validation and audit.
4. LangGraph emphasizes visible domain transitions and checkpoint ownership.
5. The Agents SDK emphasizes the model/tool loop and serializable run state.
6. Test doubles at the model interface can remove stochastic variance while
   exercising the real runtime.
7. Local latency and artifact size require careful interpretation.
8. Dependency constraints are architecture evidence.
9. Framework selection should follow workflow shape and customer constraints,
   not popularity.
