# SignalDesk Commit 05 — prompt-evaluation-harness

Starter package for treating SignalDesk prompts like versioned software artifacts.

This package builds on the Commit 04 lesson:

- deterministic Customer 360 facts remain the source of truth
- the LLM interprets bounded facts, but does not calculate metrics
- structured output is required, but is not enough
- prompt changes must be measured against a fixed eval suite

## Scope

Included:

- Prompt V1 frozen as `commit04_v1_frozen`
- Prompt V2 placeholder with explicit hypothesis notes
- 50 curated JSONL eval cases
- runner for real OpenAI Responses API calls
- local mock mode for harness sanity checks
- metrics for classification, evidence coverage, schema validity, latency, tokens, and cost
- comparison report with regressions and per-case deltas

Not included:

- RAG
- embeddings
- agents
- tool calling
- policy retrieval
- orchestration frameworks

## Baseline

Keep Commit 04's measured winner as the baseline:

```text
model = gpt-5.6-luna
reasoning = none
prompt = commit04_v1_frozen
```

## Suggested repo locations

```text
evals/commit05/cases.jsonl
evals/commit05/make_cases.py
evals/commit05/runner.py
evals/commit05/metrics.py
evals/commit05/compare.py
evals/commit05/reports/.gitkeep
src/llm/prompt_versions/v1.py
src/llm/prompt_versions/v2.py
requirements-commit05.txt
```

## Generate the 50-case suite

This follows the repo's Commit 04 pattern: cases store customer IDs and rubric
expectations; the runner loads Customer 360 snapshots from DuckDB.

```bash
python -m evals.commit05.make_cases \
  --database data/warehouse/signaldesk.duckdb
```

## Run against the model

```bash
export OPENAI_API_KEY=...

python -m evals.commit05.runner \
  --prompt-version v1 \
  --database data/warehouse/signaldesk.duckdb \
  --model gpt-5.6-luna \
  --reasoning-effort none

python -m evals.commit05.runner \
  --prompt-version v2 \
  --database data/warehouse/signaldesk.duckdb \
  --model gpt-5.6-luna \
  --reasoning-effort none
```

Then compare the two generated result files:

```bash
python -m evals.commit05.metrics \
  --results evals/commit05/reports/results_v1_gpt_5_6_luna_none.jsonl

python -m evals.commit05.metrics \
  --results evals/commit05/reports/results_v2_gpt_5_6_luna_none.jsonl

python -m evals.commit05.compare \
  --baseline evals/commit05/reports/results_v1_gpt_5_6_luna_none.jsonl \
  --candidate evals/commit05/reports/results_v2_gpt_5_6_luna_none.jsonl
```

## Commit 05 definition of done

- 50 cases are fixed before prompt tuning
- Prompt V1 is frozen and remains runnable
- Prompt V2 has a written change hypothesis before edits
- V1 and V2 use the same model, reasoning setting, schema, and cases
- comparison report lists improvements and regressions
- final decision is measured: keep V1, adopt V2, or iterate again
