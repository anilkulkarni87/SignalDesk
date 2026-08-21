# Experiments and Evidence

SignalDesk treats prompts, retrievers, tools, agent loops, workflows, and
failure behavior as measurable software surfaces. A passing curated test is
evidence for that contract, not proof of general correctness.

## Claim language

| Label | Meaning |
|---|---|
| Measured | Produced by a checked-in benchmark, test, report, or CI run |
| Demonstrated | Observed in the local workflow without a representative study |
| Inferred | An engineering conclusion supported by several measurements |
| Hypothesis | Requires representative users, data, or business experiments |

## Selected scorecard

| Area | Result | Boundary |
|---|---:|---|
| Synthetic data | 100,000 customers; 7,005,497 rows | Repeatable test substrate |
| Lexical retrieval | Recall@5 68%; MRR 0.4697 | Curated 50-query benchmark |
| Vector retrieval | Recall@5 98%; MRR 0.9007 | Experiment, not accepted serving path |
| Grounded RAG | 100/100 final frozen questions passed | Synthetic labels and generated policies |
| Agent workflow | 50/50 tasks completed | P95 latency 9.2174s missed the target |
| Action workflow | 100 deterministic cases; zero duplicate actions | Synthetic coupon action only |
| Failure injection | 8/8 scenarios passed | Known local boundaries, not every outage |

## The important misses

- The primary RAG and agent p95 latency results did not meet the target below
  eight seconds.
- The product retained lexical retrieval even though vector retrieval performed
  better in the offline benchmark.
- Investigation time, analyst adoption, and business impact were never measured
  with real users.
- The first Commit 05 V1/V2 comparison established harness repeatability, not a
  prompt improvement.

The full evidence matrix lives in the repository's FDE evaluation document.
