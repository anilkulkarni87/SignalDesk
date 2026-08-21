# Security and Trust Boundaries

## Learning scope

SignalDesk is a synthetic learning system. This document is a threat-modeling exercise, not a security certification, privacy assessment, or claim that the repository is ready to process real customer data.

## Protected assets

| Asset | Why it matters | Current representation |
|---|---|---|
| Customer profile and event history | Could expose identity, behavior, or commercial context | Synthetic records generated inside the repository |
| Policy knowledge | Determines what the assistant may recommend | Generated, versioned knowledge documents |
| Model and tool inputs | May contain customer context or malicious instructions | Local request and execution records |
| Approval decisions | Authorize a synthetic action | Durable workflow and audit records |
| Credentials | Protect model, API, and session access | Environment variables and local secrets |
| Evaluation evidence | Supports or disproves engineering claims | Versioned reports under `evals/` |

## Trust boundaries

1. The browser is untrusted input. Authentication, request validation, and authorization belong at the API boundary.
2. The model is an untrusted planner. Structured output and tool arguments must be validated before execution.
3. Retrieved documents are untrusted context. Their content must not override application policy or tool permissions.
4. Read tools may disclose only the requested synthetic customer's bounded fields.
5. Write actions require an exact, reviewable payload and an explicit human decision.
6. Logs and traces are operational data. They must not become a second store for sensitive customer content.

## Threats and current controls

| Threat | Current learning control | Remaining real-pilot work |
|---|---|---|
| Cross-customer data access | Customer-scoped tool schemas and tests | Tenant-aware authorization, row-level policy, adversarial access tests |
| Prompt injection in retrieved text | Application-owned system instructions and bounded tools | Red-team corpus, instruction/data separation tests, output policy enforcement |
| Unsupported policy claims | Retrieved-document citations and grounded-excerpt evaluation | Approved source registry, document signing/versioning, legal review |
| PII leakage | PII-safe profile tool and synthetic data | Data inventory, minimization, retention, deletion, regional controls |
| Unauthorized write | Human approval before the synthetic coupon action | Enterprise identity, role policy, separation of duties, approval expiry |
| Duplicate or replayed action | Stable action ID and idempotency tests | Durable production store, replay protection, reconciliation process |
| Session theft or forgery | Access code and signed local session | SSO, short-lived sessions, secure cookies, CSRF review, device policy |
| Secret disclosure | Environment-variable configuration | Managed secret store, rotation, least privilege, leak scanning |
| Excessive tool use | Explicit tool schemas, bounds, and agent evaluation | Per-user quotas, anomaly detection, budget enforcement |
| Dependency or service failure | Timeouts, typed failures, health/readiness checks | Multi-zone strategy, dependency SLOs, paging and incident ownership |

## Permission model

| Actor | Read customer data | Search policy | Propose action | Approve action | Execute action |
|---|---:|---:|---:|---:|---:|
| Browser user | Through authenticated API | Through authenticated API | Yes, in the learning UI | Yes, as the local reviewer | No |
| Model | Only through bounded tools | Through bounded search | May recommend or call an approval-gated tool | No | No |
| API/workflow | Enforces tool contracts | Enforces corpus boundary | Validates exact payload | Records decision | Only after approval |
| MCP client | Four read-only tools | Yes | No | No | No |

The repository does not implement enterprise roles. The table describes the intended separation demonstrated by the local workflow, not a complete authorization system.

## Data handling rules

- Keep all demonstrations on generated data and generated knowledge.
- Never commit API keys, access codes, session secrets, cookies, or exported traces.
- Pass secrets through the environment and rotate any value accidentally disclosed.
- Avoid logging raw prompts, complete profiles, or free-form approval reasons in a real deployment.
- Define retention and deletion periods before introducing real customer data.
- Treat model-provider data handling, geographic processing, and retention as explicit vendor-review questions.

## Pilot security gate

A real pilot should not start until the team has evidence for all of the following:

- Named data owner and system owner.
- Approved data classification and minimum field list.
- Enterprise authentication and role mapping.
- Customer-level authorization tests.
- Managed secrets and rotation procedure.
- Prompt-injection and cross-customer red-team tests.
- Audit retention, access, and deletion policy.
- Incident response owner and escalation path.
- Legal, privacy, and vendor review where applicable.
- A kill switch that disables model calls and all actions independently.

## Evidence

- The read-only MCP boundary is described in [Commit 14](../../README_COMMIT14.md).
- Local API and session boundaries are described in [Commit 15](../../README_COMMIT15.md).
- Human approval and idempotency are evaluated in [Commit 12](../../README_COMMIT12.md).
- Failure behavior and boundary coverage are recorded in [Commit 17](../../README_COMMIT17.md).

