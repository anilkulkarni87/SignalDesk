# Guided Labs - Beta

The guided beta turns six anchor milestones into a zero-model-call learning
path. It is intentionally smaller than the complete 18-chapter journey so that
the lesson format can be tested before the rest of the course is expanded.

## Available lessons

| Lesson | Topic | Learner outcome |
|---|---|---|
| 01 | Problem-first FDE discovery | Frame a workflow, metric, countermetric, and authority boundary |
| 02 | Synthetic customer data | Separate structural, semantic, and scale truth |
| 04 | Structured LLM evaluation | Distinguish schema, behavior, evidence, latency, and cost |
| 06 | Retrieval from first principles | Compare Recall@K, MRR, latency, and serving fit |
| 10 | Bounded agent loops | Explain tools, limits, provenance, and non-authority |
| 18 | FDE capstone | Present evidence, failures, limitations, and the next decision |

## Learning contract

Every lesson follows:

```text
problem -> first principles -> build -> measure -> break -> explain -> ship
```

Technical checks read frozen evidence and run deterministic tests. Completion
requires a learner-written reflection because a passing repository test does
not establish understanding.

## Cost and setup

No course check calls a model or requires an OpenAI key. The optional live
experiments remain clearly separated from the default learning path.
