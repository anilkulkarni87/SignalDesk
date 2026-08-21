# SignalDesk FDE Delivery Pack

> Learning scope: SignalDesk is a synthetic portfolio system. NovaCart is
> fictional, no real customer interviews occurred, no real customer data is
> used, and no business impact has been observed. This pack rehearses the work
> of explaining an AI system; it is not a production handoff.

Commit 18 turns the preceding engineering milestones into one defensible story
for a mixed executive and engineering audience.

## The story in one sentence

SignalDesk tests whether a bounded, evidence-grounded assistant over a
synthetic customer data platform could reduce the time needed to investigate an
at-risk customer while keeping policy interpretation and consequential actions
reviewable by a human.

## How to use this pack

Read in this order for a full walkthrough:

1. [Discovery](discovery.md) - the fictional workflow and assumptions.
2. [Requirements](requirements.md) - what was requested and what exists.
3. [Architecture](architecture.md) - data, retrieval, agent, API, and UI.
4. [Security](security.md) - trust boundaries, controls, and gaps.
5. [Evaluation](evaluation.md) - measured results and claim limits.
6. [Deployment](deployment.md) - how the local learning stack is packaged.
7. [Runbook](runbook.md) - how to operate and diagnose the demo.
8. [ROI](roi.md) - hypothetical value model and validation plan.
9. [Known limitations](known_limitations.md) - what is not proven.
10. [Roadmap](roadmap.md) - the path from learning system to pilot evidence.
11. [Ten-minute demo](demo.md) - a timed presentation script.

## Evidence language

Every claim should fit one of these labels:

| Label | Meaning |
|---|---|
| Measured | Produced by a checked-in report, test, CI run, or benchmark. |
| Demonstrated | Observed in a local workflow but not a representative study. |
| Inferred | A reasoned engineering conclusion from measured evidence. |
| Hypothesis | A proposition that requires a real pilot or customer data. |

The pack never converts a synthetic evaluation score into a real-world quality
claim and never converts model latency into human time saved.

## Frozen behavioral contract

Commit 18 changes documentation only. It preserves:

```text
model             gpt-5.6-luna
reasoning effort  none
prompt             commit10_v4_campaign_evidence_budget
retrieval          lexical_current_approved in the serving product
agent runtime      LangGraph
action authority   exact-payload human approval
```

Historical vector and alternate-runtime experiments remain evidence for design
decisions, not hidden serving dependencies.

## Source evidence

The main checked-in evidence is under:

```text
docs/benchmarks/
evals/commit05/reports/
evals/commit06/reports/
evals/commit07/reports/
evals/commit09/reports/
evals/commit10/reports/
evals/commit11/reports/
evals/commit12/reports/
evals/commit13/reports/
evals/commit17/reports/
LEARNING_LOG.md
```

## Definition of done

This delivery pack is complete when:

- all ten roadmap documents and the demo script exist;
- material numerical claims point to repository evidence;
- product boundaries and security gaps are explicit;
- ROI is presented as a sensitivity model, not achieved value;
- the demo can be run without improvising architecture or safety claims;
- automated checks verify required files and local Markdown links.
