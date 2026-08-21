# Lesson 04 - Structured LLM Calls and Behavioral Evaluation

> Learning scope: frozen reports came from synthetic cases and one model
> configuration. They do not establish general or production accuracy.

## Outcome

You will be able to place an LLM behind a typed boundary and distinguish API
success, schema validity, behavioral agreement, evidence coverage, latency, and
cost.

## Problem

SQL returns the same deterministic calculation for the same input. A model call
can return plausible but differently phrased, incomplete, or incorrect output.
"The response looked good" is therefore not a regression contract.

## First principles

Keep deterministic facts below the probabilistic boundary:

```text
Customer 360 JSON
  -> model selects and interprets relevant evidence
  -> strict structured output
  -> application resolves factual values
  -> evaluator scores separate behaviors
```

Schema validity answers whether the response can be consumed. Risk agreement
and evidence coverage answer different questions about its behavior.

## Build

Inspect:

- [Single request entry point](../../../../run_one.py)
- [Frozen cases](../../../../evals/commit04/cases_v2.jsonl)
- [Evaluation report](../../../../evals/commit04/report_luna_none_v2.json)
- [Experiment plan](../../../../docs/commit04_experiment_plan.md)

Trace one case from input, through the response schema, to its scored metrics.
Identify which fields the application could verify deterministically.

## Measure

Predict whether schema validity or required-evidence coverage will be higher.
Then inspect the frozen 30-case result:

```text
API success                100.0%
schema validity            100.0%
risk accuracy               90.0%
required evidence           76.67%
p95 latency                  4.0253 seconds
```

One aggregate score would hide the evidence-coverage weakness.

## Break

Imagine a response with the correct risk label but unsupported evidence. Decide
which metrics pass and which fail. Then consider the opposite: valid evidence
with the wrong final classification.

Also ask what changes when the same 30 cases are run twice. A single completion
per case does not measure model variance.

## Explain

Answer in your own words:

1. Why is schema validity necessary but insufficient?
2. Which values should never be calculated by the model?
3. Why must cases, model, reasoning effort, and schema remain frozen during a comparison?

## Ship

Keep an evaluation contract that names the input set, model configuration,
schema, metrics, per-case failures, cost, and regression definition.

## Verify

```bash
python run_course.py check 04
```

This command reads frozen evidence and makes no API call.

## Continue

Lesson 05 will convert prompt comparisons into a dedicated regression lesson.
The pilot path continues to retrieval:

```bash
python run_course.py start 06
```

Deep reading: [LLMs for Data Engineers](../../../../docs/blog/04-llms-for-data-engineers-from-sql-determinism-to-probabilistic-systems.md).
