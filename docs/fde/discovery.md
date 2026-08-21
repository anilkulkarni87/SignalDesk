# Discovery

> Learning scope: this is a fictional discovery record for NovaCart. It models
> the questions an FDE should ask; it is not evidence from real stakeholders.

## Executive problem statement

NovaCart is assumed to receive about 2,000 customers from an existing at-risk
model each week. Retention specialists investigate roughly 15%, or 300
customers, because each investigation is assumed to take 20-30 minutes.

The unresolved problem is investigation capacity and consistency, not customer
risk prediction. SignalDesk therefore starts after the upstream model and helps
an analyst assemble customer facts, inspect applicable policy, explain warning
signals, and prepare a reviewable next step.

## Personas

| Persona | Decision | Primary risk |
|---|---|---|
| Retention specialist | What should happen next for this customer? | Acting on incomplete or unsupported evidence. |
| Retention manager | Is the investigation process efficient and reliable? | Scaling cost without measuring quality or outcomes. |
| Support specialist | What issue requires follow-up? | Repeating investigation work or receiving poor context. |

## Workflow observed in the fictional brief

```text
weekly at-risk list
  -> collect customer history
  -> compare current and prior behavior
  -> inspect support and policy context
  -> form an evidence-backed explanation
  -> choose or draft a next step
  -> human review
  -> synthetic action ledger
```

The original process baseline and desired outcomes are documented in
[customer_problem.md](../customer_problem.md),
[discovery_notes.md](../discovery_notes.md), and
[success_metrics.md](../success_metrics.md).

## Initial hypotheses

1. Deterministic Customer 360 metrics can remove repeated manual calculation.
2. Retrieval can make current policy easier to inspect if citations remain
   traceable to approved sources.
3. A tool-using model can decide which bounded read operations are needed for a
   question without receiving database access.
4. Human approval can preserve authority over consequential actions.
5. An integrated workspace can reduce human investigation time.

Hypotheses 1-4 have synthetic technical evidence. Hypothesis 5 remains
unvalidated because no timed analyst study was performed.

## Discovery questions for a real engagement

### Workflow

- Who creates the at-risk list, and how often?
- What event marks the start and end of an investigation?
- Which systems do specialists open today?
- Which decisions are common, exceptional, or prohibited?
- What information causes a specialist to stop and escalate?

### Data

- Which customer identifiers are authoritative?
- What is the acceptable freshness for purchases, events, consent, and support?
- Which fields are PII, sensitive, or jurisdiction-restricted?
- How are late events and identity merges corrected?
- Which semantic definitions already have business ownership?

### Policy and actions

- Which documents are authoritative and who approves them?
- How are policy version, region, and effective date represented?
- Which actions require approval, dual control, or segregation of duties?
- What is the source of truth for action completion and reversal?

### Operations

- What are expected concurrency, availability, and recovery objectives?
- Which identity provider, secret manager, log platform, and deployment target
  are already approved?
- What data retention and deletion requirements apply?
- Who owns incident response and model-quality review?

### Outcomes

- What is the current median and p95 investigation time?
- How often do specialists agree with a proposed next step?
- What downstream outcome can be causally attributed to the intervention?
- What value threshold justifies a pilot or wider rollout?

## What changed during implementation

| Initial simplification | What the experiments taught |
|---|---|
| A prompt alone could explain risk. | Structured output still needed evidence checks and frozen evals. |
| Correct retrieval implied grounded answers. | Citation identity, policy-family coverage, and unsupported claims required separate metrics. |
| Tool calling implied useful agency. | Subject binding, schemas, limits, and unnecessary-call metrics defined the real boundary. |
| A working action button implied safety. | Recommendation, authorization, idempotency, recovery, and audit were separate concerns. |
| Local success implied deployability. | Clean CI exposed undeclared dependencies and ambient timezone behavior. |

## Discovery conclusion

The defensible learning conclusion is narrow: SignalDesk demonstrates the
technical shape of an evidence-backed investigation workflow over synthetic
data. A real engagement would return to discovery before reusing its labels,
policies, security model, or ROI assumptions.
