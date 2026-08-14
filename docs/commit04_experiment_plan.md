# Commit 04 Experiment Plan

## Goal

Learn the LLM request lifecycle against deterministic Customer 360 JSON before
adding RAG, tools, or an agent framework.

## Questions

1. Can the model return a strict typed schema reliably?
2. How much latency does one assessment add?
3. How many input/output/reasoning tokens does it consume?
4. What is the estimated cost per assessment?
5. Does the model consistently interpret deterministic warning signals?
6. What changes when reasoning effort changes?
7. What does streaming look like at the raw API-event level?

## Baseline model

Default:

```text
gpt-5.6-luna
reasoning effort = none
```

Why:

- this task is small, structured, and high-volume rather than frontier reasoning,
- we want a latency/cost baseline before spending more reasoning tokens,
- the model is configurable so the same 30 cases can later be compared against
  Terra or Sol.

## Evaluation dataset

30 cases from `customer_360`:

- 6 multiple-warning-signal cases → expected HIGH
- 6 purchase-decline-only cases → expected MEDIUM
- 6 engagement-decline-only cases → expected MEDIUM
- 6 support-attention-only cases → expected MEDIUM
- 6 no-warning-signal cases → expected LOW

These expected labels are an evaluation rubric for this commit.

They are **not** a production churn model and do not use hidden generator truth.

## Output schema

The model returns:

```text
risk_level
summary
evidence[]
recommended_investigation[]
limitations[]
```

The model is not allowed to output arbitrary evidence keys.

It selects from a bounded set of deterministic Customer 360 feature names.
Application code then attaches the actual feature values.

This prevents the model from becoming the source of truth for customer metrics.

## Measurements

Track:

```text
API success rate
schema-valid rate
risk-label accuracy
required-evidence coverage
evidence-feature validity
mean / p50 / p95 latency
input tokens
output tokens
reasoning tokens
estimated cost/request
retry attempts
```

## Experiments

Run baseline first:

```text
Luna + reasoning none
```

Then compare at least one setting:

```text
Luna + reasoning low
```

Optionally compare:

```text
Terra + reasoning none/low
```

Do not change model and prompt simultaneously when trying to understand a
quality difference.

## Important limitation

The 30-case rubric tests whether the model follows our explicit interpretation
rules over deterministic features.

It does not prove:

- real churn prediction accuracy,
- causal intervention effectiveness,
- policy correctness,
- RAG quality,
- agent task completion.
