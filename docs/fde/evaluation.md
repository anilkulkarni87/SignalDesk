# Evaluation and Evidence

## Learning scope

This evaluation summarizes synthetic experiments already committed to SignalDesk. It distinguishes measured repository results from hypotheses about real analyst productivity or customer outcomes.

## Claim discipline

| Label | Meaning |
|---|---|
| Measured | Produced by a versioned runner against frozen synthetic inputs |
| Demonstrated | Observed in a local workflow, without a controlled benchmark |
| Inferred | A conclusion supported by several measurements but not directly measured |
| Hypothesis | Must be tested with representative users or production-like data |

Passing a curated test means the implementation satisfied that test contract. It does not prove general correctness, production reliability, or business impact.

## Evidence ladder

| Milestone | What was measured | Result | Interpretation |
|---|---|---:|---|
| Commit 02 | Synthetic data generation | 100,000 customers; 7,005,497 rows; semantic and structural checks passed | A repeatable test substrate exists |
| Commit 05 | Prompt harness repeatability | Frozen cases, versioned prompts, and comparison reports | The original V2 was behaviorally identical; this proves repeatability, not prompt improvement |
| Commit 06 | Retrieval benchmark | Lexical Recall@5 68%, MRR 0.4697; vector Recall@5 98%, MRR 0.9007 | Vector retrieval improved curated benchmark quality at higher latency |
| Commit 07 | Grounded answer evaluation | 100/100 API calls, risk labels, answers, citation grounding, and unsupported-claim checks passed | The frozen RAG contract passed its curated suite |
| Commit 09 | Tool contract benchmark | 525 executions; valid and invalid input behavior 100%; 0 failures | Deterministic tools met their bounded contracts |
| Commit 10 | Agent evaluation | 50 cases; task completion 100%; unnecessary-tools-empty 98%; p95 9.2174s | Task quality passed; one efficiency metric and latency remained imperfect |
| Commit 11 | Runtime comparison | LangGraph retained task metrics and reached 100% unnecessary-tools-empty | Orchestration could change without a behavioral regression in this suite |
| Commit 12 | Approval workflow | 100 cases; gating, outcome, audit, recovery 100%; duplicate action 0 | Synthetic actions were approval-gated and idempotent under tested paths |
| Commit 13 | Runtime parity | 20 cases per runtime; parity true; duplicate action 0 | Two runtime implementations met the same synthetic workflow contract |
| Commit 15 | Local application | Search, investigation, action review, and audit were demonstrated | The components form a usable local workflow |
| Commit 16 | Observability | Local run, tool, retrieval, token, cost, and human-evaluation views | A reviewer can inspect a local run; this is not production monitoring |
| Commit 17 | Failure injection and API boundaries | 8/8 failure scenarios; 92% API boundary coverage; 148 tests; liveness smoke 100/100 | Known failure paths degrade predictably in the tested local environment |

## Current scorecard

| Success metric | Target | Evidence | Status |
|---|---:|---:|---|
| Retrieval Recall@5 | > 85% | 98% for vector benchmark | Passed in experiment |
| Grounded task success | > 90% | 100% on Commit 07 and Commit 10 curated suites | Passed in synthetic evaluation |
| P95 end-to-end latency | < 8 seconds | 8.2808s Commit 07; 9.2174s Commit 10 | Not met |
| Investigation time | < 3 minutes from fictional 20-30 minute baseline | Not measured with users | Unknown |
| Analyst adoption | Defined during discovery | No real analysts enrolled | Unknown |
| Retention or revenue effect | Positive causal impact | No business experiment | Unknown |

The vector result is an experiment. The accepted serving path remains the deterministic current-approved lexical retriever, so its lower benchmark recall must remain visible rather than being replaced by the vector headline.

## Known evaluation risks

- Cases, expected labels, generated customer data, and generated policies come from the same learning project.
- Curated selectors can accidentally make evidence ambiguous. Commit 05's first 50-case comparison had broader warning evidence in 24 cases and a missing required selector in `multiple_warning_signals_03`; it is retained as a repeatability experiment.
- Most model suites use one completed run per frozen case, so stochastic variance is under-sampled.
- Automated graders test explicit contracts, not every way an answer can mislead a person.
- Latency and cost were measured locally and are sensitive to network, provider, caching, and concurrency.
- No independent subject-matter expert reviewed the policy answers.

## Pilot evaluation design

1. Freeze a representative, de-identified pilot set before changing prompts or retrieval.
2. Have two domain reviewers independently label risk, evidence, and acceptable actions.
3. Record inter-rater agreement and adjudicate disagreements without viewing model output.
4. Compare the assisted workflow with the current workflow on time, accuracy, escalation, and rework.
5. Separate offline quality, online reliability, user adoption, and business outcomes.
6. Publish failures and regressions by cohort; do not report only an average.
7. Define stop conditions for cross-customer access, unsupported policy advice, or unauthorized action.

## Primary artifacts

- [Commit 06 retrieval benchmark](../../evals/commit06/reports/retrieval_benchmark.json)
- [Commit 07 final RAG report](../../evals/commit07/reports/rag_v6_report.json)
- [Commit 09 tool benchmark](../../evals/commit09/reports/tool_benchmark.json)
- [Commit 10 agent report](../../evals/commit10/reports/v4_full_report.json)
- [Commit 11 runtime comparison](../../evals/commit11/reports/langgraph_report.json)
- [Commit 12 action evaluation](../../evals/commit12/reports/action_report.json)
- [Commit 13 runtime comparison](../../evals/commit13/reports/runtime_comparison.json)
- [Commit 17 failure report](../../evals/commit17/reports/failure_injection_report.json)
- [Success metric definitions](../success_metrics.md)
