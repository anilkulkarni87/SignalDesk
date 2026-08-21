# Requirements Traceability

> Learning scope: statuses describe this repository, not production acceptance
> by a customer. The original requirements are hypotheses from a fictional
> discovery exercise.

## Status definitions

| Status | Meaning |
|---|---|
| Demonstrated | A local end-to-end or deterministic workflow exists. |
| Measured | A checked-in evaluation or test measures the requirement. |
| Partial | A bounded learning implementation exists with known missing pieces. |
| Not validated | The result requires real users, traffic, data, or outcomes. |

## Functional traceability

| Requirement | Status | Repository evidence | Remaining gap |
|---|---|---|---|
| Inspect customer profile and history | Demonstrated | `src/tools/cdp.py`, Commit 15 UI | Real CDP integration, freshness SLA, PII policy. |
| Compare deterministic customer signals | Measured | Customer 360 tests and Commit 09 tool benchmark | Business ownership of feature definitions. |
| Retrieve applicable policy | Measured synthetically | Commit 06 retrieval and Commit 07 RAG reports | Real policy corpus, region/effective-date governance. |
| Produce an evidence-backed explanation | Measured synthetically | Commit 07 and Commit 10 evals | Independent labels and human adjudication. |
| Select bounded read tools | Measured synthetically | Commit 10 full agent report | Adversarial and stochastic reliability study. |
| Keep action authority with a human | Measured deterministically | Commit 12 action report | Enterprise identity, role policy, real action system. |
| Persist investigation and evaluation records | Demonstrated | Commit 15/16 SQLite stores and UI | Shared durable database and retention policy. |
| Expose bounded capabilities over MCP | Measured locally | Commit 14 integration tests | OAuth service, TLS, tenant scopes, deployment. |
| Search and investigate in an analyst UI | Demonstrated locally | Commit 15 browser workflow | Timed usability study and accessibility audit. |
| Observe latency, tools, retrieval, cost, and errors | Demonstrated locally | Commit 16 dashboard | External traces, alerts, multi-user operations view. |

The full original requirement set remains in [requirements.md](../requirements.md).

## Non-functional traceability

| Requirement | Target | Current evidence | Honest status |
|---|---:|---|---|
| Investigation p95 latency | `<8s` | Commit 10 p95 `9.2174s`; Commit 07 RAG p95 `8.2808s` | Target not met in those frozen live runs. |
| Task success | `>85%` | Commit 10 frozen 50-task completion `100%` | Passed on one curated synthetic run only. |
| Unsupported-answer rate | `<5%` | Commit 07 V6 unsupported-policy-claims empty `100%` | Passed on the frozen 100-question suite. |
| Retrieval Recall@5 | `>85%` | Commit 06 vector `98%`; lexical `68%` | Vector experiment passed; serving product later accepted lexical retrieval for bounded known intents. |
| API boundary coverage | `>80%` | Commit 17 `92%` | Passed for `src/api`, not whole-repository coverage. |
| Unhandled exceptions | `<1%` | 8/8 injected failures and 100/100 liveness smoke with zero unhandled exceptions | Local deterministic evidence only. |
| Human investigation time | `<3 min` | No representative timed study | Not validated. |
| Investigation coverage | `>=80%` | No operating workflow or real at-risk queue | Not validated. |

## Contract invariants

The current learning system intentionally preserves:

- deterministic metrics are computed outside the LLM;
- customer-scoped tools cannot switch subjects;
- retrieved content is treated as untrusted data;
- only current approved knowledge is exposed;
- model rounds, tool calls, result sizes, and retries are bounded;
- generated evidence must resolve to actual tool output;
- actions require exact-payload human approval;
- retries cannot duplicate a synthetic action;
- runtime completion and human quality evaluation remain separate.

## Requirements not implemented as real capabilities

- automatic retention-offer selection in the analyst product;
- real campaign, coupon, support, account, or messaging execution;
- manager analytics over real outcomes;
- enterprise SSO and tenant authorization;
- distributed persistence, rate limits, or idempotency;
- production data governance, deletion, or legal controls;
- causal measurement of retention lift.

## Acceptance recommendation

For this learning milestone, accept the delivery pack when its claims are
traceable and its gaps are explicit. Do not use this traceability table as a
go-live checklist for an actual customer deployment.
