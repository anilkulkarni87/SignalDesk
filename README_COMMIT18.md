# SignalDesk Commit 18 - FDE Delivery Pack

Commit 18 asks the final roadmap question:

> Can we turn a sequence of technical experiments into an honest customer,
> engineering, and operating decision?

SignalDesk remains a synthetic learning system. NovaCart is fictional, no real
customer interviews or production data were used, and no business impact was
measured. This milestone packages evidence and uncertainty; it does not add AI
behavior or claim production readiness.

## What changed

The new [FDE delivery pack](docs/fde/README.md) contains:

```text
discovery             fictional workflow, users, and open questions
requirements          traceability from needs to repository evidence
architecture          accepted serving path and trust boundaries
security              threats, current controls, and pilot gates
evaluation            measured results, misses, and evidence risks
deployment            reproducible local startup and verification
runbook                diagnosis, recovery, and evidence capture
ROI                    transparent hypothetical value model
known limitations     explicit technical and product gaps
roadmap                evidence-gated path toward a real pilot
demo                   ten-minute presentation and fallback script
```

Commit 18 also adds a learning-log chapter, a blog article, and automated checks
for required documents, frozen configuration, scope labels, and local links.

## Frozen behavior

No prompt, retriever, model, tool, workflow, API, or UI behavior changes in this
commit:

```text
model             gpt-5.6-luna
reasoning effort  none
prompt             commit10_v4_campaign_evidence_budget
retrieval          lexical_current_approved
agent runtime      LangGraph
action authority   exact-payload human approval
```

Vector retrieval and the Agents SDK remain measured experiments rather than
accepted serving dependencies.

## Evidence snapshot

| Area | Measured result | Honest interpretation |
|---|---:|---|
| Data substrate | 100,000 customers; 7,005,497 rows | Repeatable synthetic test data |
| Retrieval | Vector Recall@5 98%; lexical 68% | Experimental vector advantage; product still serves lexical |
| Grounded RAG | 100 curated questions passed final rubric | Frozen synthetic contract, not general correctness |
| Tool contracts | 525 executions; 0 failures | Bounded deterministic tools met tested contracts |
| Agent tasks | 50/50 completed; p95 9.2174s | Quality passed; latency target below 8s did not |
| Approval workflow | 100 cases; 0 duplicate actions | Synthetic approval and idempotency paths passed |
| Hardening | 8/8 failures; 148 tests; 92% API coverage | Known local boundaries behaved as designed |
| Human productivity | Not measured | Fictional ROI remains a hypothesis |

Commit 05's initial V1/V2 result is classified as harness repeatability, not
prompt improvement, because the placeholder prompts were behaviorally
identical and the first case selectors included ambiguous evidence.

## Read the pack

Start at [docs/fde/README.md](docs/fde/README.md), then use the
[ten-minute demo](docs/fde/demo.md) to present the journey.

The key decision document is [docs/fde/roadmap.md](docs/fde/roadmap.md): the
next useful step is real discovery and independent evaluation, not another
framework or feature.

## Verify

```bash
python -m pytest tests/commit18 -q
python -m pytest -q
```

These checks verify packaging consistency. They do not rerun paid model calls
or turn documentation assertions into customer evidence.

Measured after adding the four Commit 18 packaging checks:

```text
Commit 18 focused tests   4 passed
full repository tests    152 passed
external model calls     0
```

The 148-test value in the evidence snapshot is the final Commit 17 hardening
baseline. The 152-test value is the current repository total.

## Definition of done

- Ten required roadmap documents and one timed demo exist.
- Every document carries the synthetic learning boundary.
- Local Markdown evidence links resolve.
- Material metrics include limitations and failed targets.
- Deployment and runbook commands match the accepted local architecture.
- ROI is a formula and sensitivity analysis, not an achieved benefit.
- The roadmap ends with evidence-gated validation stages.
