# Code Companion

SignalDesk is easier to understand as a sequence of engineering boundaries than
as a catalog of frameworks. This companion connects each boundary to a small
set of source files, a real execution path, and the evidence produced by the
repository.

Start with the concept you need. You do not need to read the repository from
top to bottom.

**Choose a subsystem:** [Synthetic data](#1-synthetic-customer-data) ·
[Customer 360](#2-customer-360-semantic-layer) ·
[LLM evaluation](#3-structured-llm-evaluation) ·
[Vector search](#4-vector-search) · [RAG](#5-retrieval-augmented-generation) ·
[Tools and agents](#6-bounded-tools-and-agents) ·
[State and approval](#7-stateful-workflow-and-human-approval) ·
[MCP](#8-mcp-integration) · [Product](#9-product-and-observability)

## Local setup

Create one environment for the completed repository:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-commit17.txt
```

The default commands below avoid model calls. Full LLM runs require
`OPENAI_API_KEY`, and vector indexing also requires the local pgvector service.

## 1. Synthetic customer data

**Question:** How do you create safe test data that contains realistic business
behavior rather than unrelated random rows?

The generator first assigns hidden customer behavior patterns, then makes
profiles, orders, sessions, support tickets, consent, and campaign events agree
with those patterns. A fixed seed makes failures reproducible. Duplicate,
late-arriving, and null records are deliberate test conditions.

**Read in this order:**

1. [`generate_synthetic_cdp_v5.py`](https://github.com/anilkulkarni87/SignalDesk/blob/main/data/generator/generate_synthetic_cdp_v5.py) owns the entities, behavioral correlations, quality defects, and deterministic seed.
2. [`validate_synthetic_cdp.py`](https://github.com/anilkulkarni87/SignalDesk/blob/main/data/generator/validate_synthetic_cdp.py) checks structural and semantic invariants.
3. [`02-building-a-synthetic-cdp-for-ai-engineering-experiments.md`](https://github.com/anilkulkarni87/SignalDesk/blob/main/docs/blog/02-building-a-synthetic-cdp-for-ai-engineering-experiments.md) explains why row counts alone are weak evidence.

**Run a small sample:**

```bash
python data/generator/generate_synthetic_cdp_v5.py \
  --customers 1000 \
  --products 100 \
  --campaigns 10 \
  --output-dir data/generated/code-companion
```

Inspect `manifest.json`, then compare events for customers from different
behavior segments. The important output is cross-table consistency, not the
number of generated rows.

**Boundary:** Synthetic coherence supports controlled engineering experiments.
It does not establish that real customers behave the same way.

## 2. Customer 360 semantic layer

**Question:** Which calculations must remain deterministic before a model can
interpret customer behavior?

Customer 360 resolves identities, deduplicates events, applies as-of-time
rules, and computes reusable features. The model may interpret these features;
it may not invent their values.

**Read in this order:**

1. [`customer_360.sql`](https://github.com/anilkulkarni87/SignalDesk/blob/main/transform/sql/customer_360.sql) defines the feature grain and calculations.
2. [`build_customer_360.py`](https://github.com/anilkulkarni87/SignalDesk/blob/main/transform/build_customer_360.py) loads source data and materializes the layer.
3. [`customer_360_contract.md`](https://github.com/anilkulkarni87/SignalDesk/blob/main/docs/customer_360_contract.md) records meanings and ownership.

**Build from the sample:**

```bash
python transform/build_customer_360.py \
  --input-dir data/generated/code-companion \
  --database data/warehouse/code-companion.duckdb \
  --output data/warehouse/code-companion.parquet
```

**Boundary:** Deterministic features reduce ambiguity, but feature definitions
can still encode incorrect business assumptions.

## 3. Structured LLM evaluation

**Question:** How do you tell whether a prompt improved instead of merely
changing its wording?

SignalDesk freezes the input cases, prompt versions, model, reasoning setting,
schema, and scoring rules. Comparisons report per-case improvements and
regressions alongside latency, tokens, and cost.

**Read in this order:**

1. [`prompt_versions`](https://github.com/anilkulkarni87/SignalDesk/tree/main/src/llm/prompt_versions) contains frozen prompt implementations.
2. [`commit05/runner.py`](https://github.com/anilkulkarni87/SignalDesk/blob/main/evals/commit05/runner.py) executes the same cases against a selected prompt.
3. [`commit05/compare.py`](https://github.com/anilkulkarni87/SignalDesk/blob/main/evals/commit05/compare.py) identifies improvements and regressions.

**Inspect without a model call:**

```bash
python -m evals.commit05.metrics \
  --results evals/commit05/reports/results_v2_gpt_5_6_luna_none.jsonl
```

**Boundary:** A score is only meaningful when the cases and selectors represent
the behavior you actually care about.

## 4. Vector search

**Question:** Does semantic retrieval find relevant policy documents that
lexical matching misses?

The retrieval pipeline separates document loading, chunking, embedding,
storage, search, and measurement. Frozen relevance judgments make Recall@K and
MRR independently measurable before an LLM generates an answer.

**Read in this order:**

1. [`chunking.py`](https://github.com/anilkulkarni87/SignalDesk/blob/main/src/retrieval/chunking.py) creates bounded overlapping units.
2. [`embeddings.py`](https://github.com/anilkulkarni87/SignalDesk/blob/main/src/retrieval/embeddings.py) owns embedding requests and dimensions.
3. [`vector_store.py`](https://github.com/anilkulkarni87/SignalDesk/blob/main/src/retrieval/vector_store.py) owns pgvector persistence and similarity search.
4. [`retrieval_benchmark.py`](https://github.com/anilkulkarni87/SignalDesk/blob/main/evals/commit06/retrieval_benchmark.py) compares retrievers against frozen labels.

**Reproduce the model-free lexical baseline:**

```bash
python -m evals.commit06.retrieval_benchmark \
  --retriever lexical \
  --report /tmp/signaldesk-lexical.json
```

**Measured evidence:** Lexical Recall@5 was 68%; vector Recall@5 was 98%.
Vector retrieval improved MRR by 0.431 while adding query latency.

**Boundary:** Finding a relevant document does not prove the final answer uses
it correctly.

## 5. Retrieval-augmented generation

**Question:** How do you prove that an answer is grounded in the retrieved
policy rather than in model memory?

RAG adds bounded context construction, resolvable citations, exact excerpt
validation, and unsupported-claim checks. Retrieval and generation retain
separate metrics so one cannot hide the other's failures.

**Read in this order:**

1. [`query_planner.py`](https://github.com/anilkulkarni87/SignalDesk/blob/main/src/retrieval/query_planner.py) translates a customer question into bounded retrieval needs.
2. [`commit07/runner.py`](https://github.com/anilkulkarni87/SignalDesk/blob/main/evals/commit07/runner.py) joins customer evidence, retrieved context, and structured generation.
3. [`commit07/metrics.py`](https://github.com/anilkulkarni87/SignalDesk/blob/main/evals/commit07/metrics.py) scores answer, citation, excerpt, and unsupported-claim behavior separately.

**Run the retrieval gate before generation:**

```bash
python -m evals.commit07.retrieval_gate \
  --database data/warehouse/signaldesk.duckdb \
  --report /tmp/signaldesk-retrieval-gate.json
```

**Boundary:** A citation can resolve to a retrieved document while still being
irrelevant to the sentence it appears to support. The excerpt and claim checks
close part of that gap.

## 6. Bounded tools and agents

**Question:** What changes when the model chooses operations rather than only
returning text?

Tools are typed, bounded APIs over deterministic business logic. The agent loop
has explicit limits, records every call, and is evaluated for tool choice,
arguments, evidence, stopping behavior, latency, and cost.

**Read in this order:**

1. [`registry.py`](https://github.com/anilkulkarni87/SignalDesk/blob/main/src/tools/registry.py) exposes the allowed tool surface.
2. [`cdp.py`](https://github.com/anilkulkarni87/SignalDesk/blob/main/src/tools/cdp.py) implements bounded customer and policy operations.
3. [`investigator.py`](https://github.com/anilkulkarni87/SignalDesk/blob/main/src/agent/investigator.py) runs the constrained model loop.
4. [`commit10/runner.py`](https://github.com/anilkulkarni87/SignalDesk/blob/main/evals/commit10/runner.py) evaluates the complete loop.

**Run deterministic tool tests:**

```bash
python -m unittest tests.commit09.test_tools -v
```

**Boundary:** Tool access gives a model capability, not authority. Consequential
actions remain outside this loop.

## 7. Stateful workflow and human approval

**Question:** When does an agent loop need explicit state and interruption?

LangGraph makes routing and checkpoints visible. The action workflow then
separates a recommendation from authorization, pauses for exact-payload human
review, records the decision, and executes approved actions idempotently.

**Read in this order:**

1. [`workflow/investigator.py`](https://github.com/anilkulkarni87/SignalDesk/blob/main/src/workflow/investigator.py) defines the investigation graph and state transitions.
2. [`actions/workflow.py`](https://github.com/anilkulkarni87/SignalDesk/blob/main/src/actions/workflow.py) defines proposal, approval, rejection, and execution paths.
3. [`actions/store.py`](https://github.com/anilkulkarni87/SignalDesk/blob/main/src/actions/store.py) persists decisions and audit events.

**Run without a model call:**

```bash
python -m unittest tests.commit11.test_workflow tests.commit12.test_actions -v
```

**Boundary:** Human approval controls execution authority. It does not make a
poor recommendation correct.

## 8. MCP integration

**Question:** How can another AI host discover and invoke SignalDesk
capabilities without receiving database access?

The MCP layer wraps four existing read-only tools with strict schemas, bearer
authentication, protected-resource metadata, and protocol-standard discovery.
It reuses domain logic rather than creating a second implementation.

**Read in this order:**

1. [`server.py`](https://github.com/anilkulkarni87/SignalDesk/blob/main/src/mcp_server/server.py) maps domain tools to MCP tools.
2. [`auth.py`](https://github.com/anilkulkarni87/SignalDesk/blob/main/src/mcp_server/auth.py) protects the HTTP boundary.
3. [`run_mcp_client_demo.py`](https://github.com/anilkulkarni87/SignalDesk/blob/main/run_mcp_client_demo.py) demonstrates discovery and invocation through a real client.

**Run the contract tests:**

```bash
python -m unittest tests.commit14.test_mcp_server -v
```

For the live localhost server and client commands, follow
[`README_COMMIT14.md`](https://github.com/anilkulkarni87/SignalDesk/blob/main/README_COMMIT14.md#run-the-server).

**Boundary:** MCP standardizes integration. It does not decide which tools an
agent should use or grant permission to perform writes.

## 9. Product and observability

**Question:** Can an operator inspect what happened after a successful or
failed investigation?

The final application exposes authenticated API contracts, an analyst
workspace, run-level tool and retrieval records, token and cost measurements,
human evaluation, readiness checks, and bounded resilience behavior.

**Read in this order:**

1. [`api/app.py`](https://github.com/anilkulkarni87/SignalDesk/blob/main/src/api/app.py) defines the HTTP surface and lifecycle.
2. [`api/service.py`](https://github.com/anilkulkarni87/SignalDesk/blob/main/src/api/service.py) coordinates the accepted domain workflow.
3. [`observability/store.py`](https://github.com/anilkulkarni87/SignalDesk/blob/main/src/observability/store.py) records inspectable run evidence.
4. [`web`](https://github.com/anilkulkarni87/SignalDesk/tree/main/web) contains the analyst and observability interface.

**Run the local API tests:**

```bash
python -m unittest tests.commit15.test_api tests.commit16.test_observability -v
```

**Boundary:** Operational controls make behavior visible and bounded. The
repository remains a synthetic learning system, not evidence of production
readiness or customer impact.

## Follow the build sequence

The companion is organized by subsystem. The [18-milestone journey](../journey/)
shows why each subsystem was introduced and which unresolved result caused the
next change. The [experiment scorecard](../experiments/) contains the accepted
measurements and failed targets.
