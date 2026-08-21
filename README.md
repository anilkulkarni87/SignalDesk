# SignalDesk

SignalDesk is a synthetic customer-intelligence learning system built one
measured milestone at a time. Commit 15 adds the first integrated analyst
product: a FastAPI backend and Next.js workspace over the accepted Customer 360,
retrieval, agent, workflow, and approval contracts.

Start with [README_COMMIT15.md](README_COMMIT15.md) for installation, run
commands, architecture, verification, and the roadmap metric.

The Commit 04 historical guide remains below, and later milestone guides are in
`README_COMMIT05.md` through `README_COMMIT14.md`. The cumulative engineering
record is in `LEARNING_LOG.md`, and the accompanying articles are under
`docs/blog`.

## Accepted model configuration

```text
model             gpt-5.6-luna
reasoning effort  none
prompt             commit10_v4_campaign_evidence_budget
```

## Current product

```text
Next.js analyst workspace
  -> authenticated FastAPI API
  -> read-only synthetic CDP
  -> bounded LangGraph investigation
  -> grounded evidence and policy sources
  -> durable exact-payload human approval
```

The system is intentionally local and synthetic. It is designed to teach and
measure architecture decisions, not to claim production readiness or real
customer impact.

## Commit 04 historical guide

This commit introduces the first probabilistic component in SignalDesk.

It deliberately does **not** include:

- RAG
- tools
- agents
- LangGraph
- policy documents
- action execution

The LLM receives deterministic Customer 360 JSON and returns a typed
investigation assessment.

## 1. Install

```bash
pip install -r requirements-commit04.txt
```

## 2. Configure API key

The OpenAI SDK reads `OPENAI_API_KEY` from the environment.

```bash
export OPENAI_API_KEY="..."
```

Optional model override:

```bash
export OPENAI_MODEL="gpt-5.6-luna"
```

Do not commit API keys.

## 3. Pick one customer and run the first request

```bash
python run_one.py \
  --database data/warehouse/signaldesk.duckdb \
  --customer-id C000000001 \
  --reasoning-effort none
```

The response contains:

- strict structured assessment,
- deterministic evidence values attached by application code,
- response ID,
- latency,
- retry attempts,
- token usage,
- estimated text-token cost.

## 4. Observe streaming directly

```bash
python stream_demo.py
```

This is intentionally a simple plain-text demo so the streaming event lifecycle
is visible without mixing it with the assessment schema.

## 5. Create the 30-case evaluation set

```bash
python evals/commit04/make_cases.py \
  --database data/warehouse/signaldesk.duckdb
```

## 6. Run the baseline evaluation

```bash
python evals/commit04/runner.py \
  --database data/warehouse/signaldesk.duckdb \
  --model gpt-5.6-luna \
  --reasoning-effort none
```

## 7. Produce metrics

```bash
python evals/commit04/metrics.py
```

## 8. Run one controlled comparison

Keep prompt + cases fixed and change only reasoning effort:

```bash
python evals/commit04/runner.py \
  --database data/warehouse/signaldesk.duckdb \
  --model gpt-5.6-luna \
  --reasoning-effort low \
  --output evals/commit04/results_luna_low.jsonl

python evals/commit04/metrics.py \
  --results evals/commit04/results_luna_low.jsonl \
  --report evals/commit04/report_luna_low.json
```

Compare:

```text
accuracy
latency
tokens
cost
```

## Design boundary

The model may choose which deterministic feature is relevant.

It may **not** invent the feature value.

For example, model output references:

```json
{
  "feature": "orders_60d",
  "interpretation": "Recent purchasing is low relative to the prior window."
}
```

Application code renders the value from Customer 360.

That keeps the deterministic/probabilistic boundary explicit.

## Definition of done

Commit 04 is complete when we have:

- one reproducible API client,
- strict structured output,
- bounded visible retry behavior,
- streaming demo,
- 30 test cases,
- schema-validity metric,
- classification metric,
- latency metric,
- token metric,
- cost metric,
- one controlled model/reasoning comparison,
- learning-log entry,
- Blog 04.
