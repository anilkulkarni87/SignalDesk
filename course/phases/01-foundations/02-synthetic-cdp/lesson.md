# Lesson 02 - Synthetic Customer Data with Semantic Truth

> Learning scope: this lesson generates fictional customers and behavior. It
> teaches data contracts and validation without handling real customer data.

## Outcome

You will be able to explain why realistic row counts are insufficient and how
structural, semantic, and scale validation establish different properties.

## Problem

An AI evaluation needs repeatable customer histories, but real customer data
introduces privacy, access, labeling, and reproducibility constraints. Random
rows are safer but can be behaviorally meaningless.

The data must support claims such as "declining engagement" in the generated
events themselves, not only in a hidden label.

## First principles

Synthetic data needs three contracts:

```text
structural truth  tables, keys, types, nulls, duplicates
semantic truth    observable behavior matches the intended pattern
scale truth       the generator and validators remain usable at target volume
```

Generator truth is an evaluation aid. It must not leak into the serving
Customer 360 contract, or the model would receive the answer rather than infer
it from evidence.

## Build

Inspect:

- [Data model](../../../../docs/data_model_v1.md)
- [Generator](../../../../data/generator/generate_synthetic_cdp_v5.py)
- [Scale benchmark](../../../../docs/benchmarks/commit02-scale-benchmark_parquet.json)

Optional small-data run:

```bash
python data/generator/generate_synthetic_cdp_v5.py \
  --customers 1000 \
  --products 100 \
  --campaigns 10 \
  --output-format parquet \
  --output-dir .course-data/small
```

The course does not require the 100,000-customer generation path for the first
lesson experience. `.course-data/` is ignored so this lab does not dirty the
learner's Git working tree.

## Measure

Before opening the benchmark, predict which quantity grows fastest with the
customer count and which semantic property is most likely to drift.

The frozen 100,000-customer run produced:

```text
customers                 100,000
total data rows            7,005,497
structural validation      passed
semantic validation        passed
```

Run the zero-call evidence check to verify that this frozen contract is still
present.

## Break

Consider these false-success cases:

- Every customer is structurally valid but behavior is indistinguishable.
- Truth labels say "declining" while recent events show stable engagement.
- Duplicate and late-arriving events disappear, making pipelines unrealistically easy.
- The serving feature layer reads generator truth directly.

For each case, identify which validator or boundary should fail.

## Explain

Answer in your own words:

1. Why can a structurally valid dataset still be useless for AI evaluation?
2. Why must generator truth stay outside the serving contract?
3. When is a 1,000-customer run sufficient, and when is 100,000 necessary?

## Ship

Keep a data contract containing table grain, identifiers, time semantics,
known-quality defects, truth-label ownership, and validation thresholds.

## Verify

```bash
python run_course.py check 02
```

The check reads the frozen benchmark; it does not regenerate the large dataset.

## Continue

The full curriculum will add Lesson 03 for the Customer 360 semantic layer. The
pilot path continues to Lesson 04:

```bash
python run_course.py start 04
```

Deep reading: [Building a Synthetic CDP](../../../../docs/blog/02-building-a-synthetic-cdp-for-ai-engineering-experiments.md).
