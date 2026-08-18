# SignalDesk Commit 12 - Human Approval and Permission Boundaries

Commit 12 adds the first consequential synthetic actions to SignalDesk. The
agent may recommend an action, but application code owns authorization and
execution.

The experiment asks:

> Can a workflow survive interruption while guaranteeing that no action occurs
> before approval, every decision is audited, and a retry never duplicates an
> action?

## Authority boundary

The action workflow supports five typed synthetic actions:

```text
ISSUE_COUPON
ENROLL_CAMPAIGN
CREATE_SUPPORT_CASE
FLAG_ACCOUNT
SEND_RETENTION_OFFER
```

The graph is:

```text
START
  -> validate_proposal
  -> record_proposal
  -> record_approval_request
  -> await_approval (LangGraph interrupt)
  -> record_decision
       -> execute_action (approved only)
       -> finish         (rejected)
  -> END
```

The interrupt payload shows the exact action plus its recommendation, reason,
and expected impact. Resume accepts only a typed `ApprovalDecision` for the same
immutable action ID.

## Exact payload binding

An action ID is a SHA-256-derived identity over the full proposal:

```text
customer + typed action payload + recommendation + reason
+ expected impact + source case + proposer
```

Changing any reviewed value invalidates the ID. The action ledger verifies the
same canonical payload again before recording a decision or executing it. The
human approves an exact command, not a general intention that the model may
reinterpret afterward.

## Durable state and separate writes

Commit 11 used process-local checkpoints. Commit 12 uses SQLite for two
different responsibilities:

```text
checkpoints.sqlite3   LangGraph thread state and interrupt/resume position
actions.sqlite3       proposals, decisions, audit records, synthetic events
```

The generated DuckDB customer warehouse remains read-only. Consequential
learning actions are written to a separate synthetic event ledger under
`data/runtime`, which is ignored by Git.

The ledger enforces one event per immutable action ID. If the event transaction
commits and the process fails before the graph checkpoints the node, recovery
retries the node and receives the existing event instead of inserting another.

## Frozen 100-case experiment

The input set reuses all 50 accepted Commit 10 customers. Each customer has two
unique action proposals:

```text
one approved path
one rejected path
```

All five action types appear 20 times. Twenty-five approved cases inject a
failure after the synthetic event commits but before the graph node returns.
Each case closes and reopens the workflow between proposal and decision, so
approval state must survive a process-level object restart.

Measured result:

```text
cases                                  100
approval gated                         100%
correct approve/reject outcome         100%
fully audited                          100%
post-commit recovery                    100% (25/25)
approved actions executed once         100%
rejected actions not executed          100%
duplicate-action rate                    0%
```

This deterministic experiment makes no model calls. It measures permission,
persistence, audit, recovery, and idempotency mechanics. It does not measure
whether the agent recommended the best business action.

The accepted investigation configuration remains:

```text
model       gpt-5.6-luna
reasoning   none
prompt      commit10_v4_campaign_evidence_budget
```

## Install and verify

```bash
python -m pip install -r requirements-commit12.txt
python -m unittest discover -s tests -v
python -m evals.commit12.make_cases
python -m evals.commit12.runner
```

The generated report is
`evals/commit12/reports/action_report.json`.

## Try the human review flow

```bash
python run_action_demo.py
```

The demo displays the exact frozen action and waits for `approve` or `reject`.
Its local checkpoint and action databases are stored under
`data/runtime/commit12/demo`. Running the same completed action again shows the
stored result instead of asking for a second decision.

## What this milestone teaches

1. Recommendation and authorization are different capabilities.
2. A model should not receive direct write authority merely because it can call
   read-only tools correctly.
3. Human approval must bind to an exact immutable payload.
4. Durable checkpoints remember where control stopped; an action ledger proves
   what was proposed, decided, and executed.
5. Idempotency is required because checkpoint completion and external writes
   cannot be assumed to commit atomically.
6. Rejection is a valid completed workflow outcome and must be audited.
7. Permission-boundary tests are deterministic and separate from model-quality
   evaluations.

## Limitations

This remains a learning system. The reviewer is a local CLI user, identity is
not authenticated, SQLite is local, audit rows are not cryptographically
tamper-evident, and the actions write only synthetic events. There is no
production coupon, campaign, support, account, or messaging integration.

Commit 13 can compare runtime approaches while preserving this permission
contract.
