# Why Production Agents Need Permission Boundaries

A model can produce a useful recommendation without being allowed to execute
it. Those are separate capabilities, and combining them too early turns a
probabilistic suggestion into an unreviewed side effect.

SignalDesk Commit 12 introduces synthetic actions only after the read-only
agent and stateful workflow have been measured. The lesson is not that adding
an approval button makes an agent production-ready. The lesson is how to place
an explicit authority boundary between reasoning and action.

## Start from first principles

An investigation answers a question. A consequential action changes state.

```text
investigation   observes data and proposes a conclusion
recommendation  describes a possible next action
authorization   grants permission for one exact action
execution       records the approved state change
```

The model may participate in the first two stages. Application code and a
human reviewer own the last two.

This separation limits the consequence of a model error. A weak recommendation
can be rejected. An automatically executed weak recommendation becomes a data
or customer-impact incident.

## Approval must name an exact command

"Approve a retention action" is too vague. The system could change the offer,
channel, discount, or customer after review while still claiming approval.

SignalDesk hashes the complete proposal into an immutable action ID:

```text
customer
typed action payload
recommendation
reason
expected impact
source investigation
proposer identity
```

The reviewer sees that exact object. Resume supplies only the decision,
reviewer, and decision reason. The workflow does not ask the model to recreate
the command after approval. Before execution, the ledger verifies that the
stored proposal still matches the action ID.

The general rule is:

> Approve values, not intentions.

## An interrupt is a control boundary

The LangGraph workflow records the proposal and approval request, then calls an
interrupt. At that point the graph returns control to the application and
stores its position in a durable SQLite checkpoint.

```text
proposal -> approval request -> INTERRUPT
                                 |
                              human decision
                                 |
                    approved -> execute
                    rejected -> finish
```

Resuming with the same thread ID continues the stored workflow. A different
action ID is rejected. A completed thread cannot receive a second decision.

The interrupt node performs no side effect before pausing because LangGraph
restarts that node when it resumes. Side effects live in completed earlier
nodes or in idempotent later nodes.

## Checkpoints and audit logs solve different problems

A checkpoint answers:

> Where should workflow computation continue?

An action ledger answers:

> What was proposed, who decided, and what state change occurred?

Commit 12 stores these responsibilities separately:

```text
LangGraph SQLite     state and resume position
action SQLite        proposal, decision, audit, synthetic event
```

The action audit for approval is:

```text
PROPOSED
APPROVAL_REQUESTED
APPROVED
EXECUTED
```

For rejection it is:

```text
PROPOSED
APPROVAL_REQUESTED
REJECTED
```

Rejection is not a failure. It is a completed and explainable outcome.

## Recovery creates an exactly-once problem

Consider this sequence:

1. The approved synthetic event commits.
2. The process fails before the graph saves the completed node checkpoint.
3. Recovery retries the execution node.

Without an idempotency key, the retry creates a duplicate action. A checkpoint
alone cannot prevent this because the external write and checkpoint are two
separate transactions.

SignalDesk uses the immutable action ID as a uniqueness key in the synthetic
event ledger. The retried node receives the existing event. Audit rows also
have a unique action-and-event-type key, so replay does not duplicate the
execution record.

This is not a distributed exactly-once guarantee. It is a local transactional
idempotency design whose behavior can be tested precisely.

## Measure the permission mechanism independently

The benchmark reuses 50 accepted customer investigations. Each customer gets
one approved and one rejected proposal, producing 100 frozen scenarios and 20
cases for each of five action types.

Twenty-five approved scenarios inject failure after the event transaction
commits. Every case closes and reopens the workflow before the decision to
prove that the interrupt is durable beyond one Python object.

The measured result is:

| Metric | Result |
|---|---:|
| Approval gated | 100% |
| Correct outcome | 100% |
| Fully audited | 100% |
| Recovery after injected failure | 100% |
| Approved actions executed once | 100% |
| Rejected actions not executed | 100% |
| Duplicate-action rate | 0% |

No model call occurs in this benchmark. That is deliberate. The experiment
tests whether permissions work for a fixed proposal, not whether a model chose
the best proposal.

The accepted investigation agent still uses `gpt-5.6-luna` with reasoning set
to `none`. Recommendation quality would require its own curated rubric,
holdout cases, and repeated stochastic evaluation.

## What the result does not prove

This is not a production authorization system. The local reviewer identity is
not authenticated. SQLite does not provide a managed multi-user permission
service. Audit records are not signed or protected from an administrator. The
five actions write synthetic CDP events rather than calling real customer
systems. There are no role policies, approval expiry, separation of duties,
rate limits, or incident controls.

The 100% result therefore supports a narrow claim:

> For the frozen scenarios, the local workflow enforced its specified approval,
> audit, persistence, recovery, and idempotency contract.

It does not support a claim of production safety or correct business judgment.

## What I learned

1. Tool availability is authority; write tools need a stronger boundary than
   read tools.
2. Human approval should bind to the exact payload that will execute.
3. Interrupts transfer control, while checkpoints preserve where control will
   resume.
4. Audit history and workflow state are complementary records.
5. External side effects must be idempotent because recovery may replay a node.
6. Rejected actions must complete cleanly and leave no side effect.
7. Authorization mechanics can and should be evaluated without model variance.
8. A perfect permission-boundary benchmark says nothing about recommendation
   quality unless that quality is evaluated separately.
