# SignalDesk Commit 07 - RAG V1

Commit 07 connects the measured Commit 06 vector retriever to structured LLM
generation.

The first-principles question is:

> After the system retrieves the right policy evidence, can the model use it to
> answer correctly, cite it exactly, and avoid unsupported claims?

This remains a bounded RAG workflow. It does not add agents, model-selected
tools, LangGraph, or automatic execution.

## System boundary

```text
explicit user question
  + deterministic Customer 360 snapshot
  -> deterministic policy query planner
  -> OpenAI query embeddings
  -> pgvector HNSW retrieval
  -> CURRENT + APPROVED filtering
  -> bounded policy context with stable quote IDs
  -> gpt-5.6-luna, reasoning=none
  -> structured assessment selecting quote IDs
  -> deterministic quote and document resolution
```

Customer facts and policy facts remain separate:

- Customer 360 controls claims about the customer.
- Retrieved policy sources control claims about process, eligibility, consent,
  escalation, and known gaps.
- The model may interpret those inputs, but it may not invent either type of
  evidence.

## What was carried forward

An early 25-case lexical policy-grounding pilot was built during Commit 06
exploration. It is preserved under `evals/commit07/pilot` rather than presented
as the final RAG result.

Commit 07 reuses its useful components:

- deterministic customer-to-policy query planning,
- policy-grounding prompt rules,
- structured policy source references,
- unsupported-policy-claim tracking.

The production evaluation path now uses the measured Commit 06 pgvector index,
not the pilot lexical retriever.

## Frozen 100-question dataset

The source is the 50 clean Commit 05 customer cases. Each customer receives two
explicit questions:

1. `risk_investigation`: explain risk and the next investigation under policy.
2. `policy_guardrails`: explain constraints and known gaps affecting a retention
   recommendation.

This creates 100 questions over 50 distinct customers. It is intentionally
described as 100 questions, not 100 independent customer profiles.

Each frozen case contains:

- question and question type,
- customer ID and Commit 05 risk category,
- expected risk level,
- required customer evidence,
- frozen deterministic policy queries,
- all expected policy families,
- any required known-gap document IDs.

Generate the file only when the Commit 05 source cases or query-planning rules
intentionally change:

```bash
python -m evals.commit07.make_cases \
  --database data/warehouse/signaldesk.duckdb
```

## Context construction

The query planner creates separate policy intents from Customer 360 flags. Each
intent is embedded and searched independently. Results are interleaved by rank
so every intent can contribute a source before one policy family fills the
context.

The context builder:

- accepts only `CURRENT` and `APPROVED` results,
- includes document metadata and the retrieved chunk,
- deduplicates at document level,
- enforces a 16,000-character budget,
- splits source text into stable quote anchors of at most 320 characters,
- includes runtime policy intents derived by the deterministic planner,
- records exactly which documents reached the model.

The model does not copy excerpts in the refined V4 path. It selects a
short context-local `quote_id` such as `Q001`; application code resolves the
corresponding document ID, chunk ID, and exact text. Short IDs avoid forcing the
structured decoder to choose among many long identifiers with identical
prefixes. Citation transport integrity remains deterministic while the semantic
relevance of the selected quote remains measurable.

## Measurable answer correctness

Commit 07 does not use a vague judge prompt for basic correctness.

An answer is correct when:

```text
expected risk level is correct
AND all required customer evidence is cited
AND any required evidence alternative is cited
```

Policy behavior is measured separately:

- expected policy documents retrieved,
- all expected policy families retrieved,
- every citation refers to a retrieved document,
- every citation selects a quote ID present in the retrieved context,
- exact excerpts and document IDs are attached deterministically,
- expected policy documents cited,
- all expected policy families cited,
- unsupported policy claims remain empty.

This separation identifies whether a failure came from retrieval or generation.

## Precommitted acceptance criteria

Before seeing the 100-question model result:

| Metric | Target |
|---|---:|
| Retrieval gate pass rate | >=90% |
| API success | 100% |
| Schema validity | 100% |
| Risk accuracy | 100% |
| Answer correctness | >=95% |
| Citation document grounding | 100% |
| Citation excerpt precision | 100% |
| Expected policy-family citation | >=90% |
| Unsupported-policy-claims empty | >=95% |
| Reasoning tokens | 0 |

Failures will be classified before changing the prompt, retrieval parameters,
context budget, or labels.

## Measured V3 baseline

The first full run is preserved as a baseline rather than overwritten:

```text
cases                                  = 100
successful API calls                   = 98
risk correctness                       = 100% of 98
answer correctness                     = 100% of 98
expected policy-family citation        = 75.51%
all exact excerpts grounded, case rate = 83.67%
per-citation exact precision           = 95.17%
unsupported claims empty               = 97.96%
reasoning tokens                        = 0
```

Failure review found:

- 2 transient API timeouts,
- 12 excerpts copied from the wrong near-duplicate retrieved document,
- 6 malformed excerpts containing invalid trailing characters,
- 24 successful responses omitting at least one planner-required policy family,
- 2 empty strings incorrectly placed in `unsupported_policy_claims`.

This demonstrates the Commit 07 learning point:

```text
correct retrieval != complete policy use != correct citation attribution
```

V4 tests one specific hypothesis without changing the frozen cases, labels,
retrieval parameters, model, reasoning setting, or context budget:

> Deterministic quote IDs will eliminate malformed and cross-attributed
> citations, while explicit runtime policy intents will raise expected-family
> citation above 90% without reducing customer-answer correctness.

The third V4 cohort attempt established the quote-anchor result:

```text
API and schema validity             = 100%
answer correctness                  = 100%
citation resolution and precision   = 100%
unsupported claims empty            = 100%
expected document/family citation   = 80%
```

V4 eliminated the citation-identity failures but did not meet the precommitted
90% family-coverage target. Two answers filled a flat six-item citation list
with duplicate retention, offer, and consent quotes while omitting the required
`GAP-001` governance intent.

V5 therefore tests a narrower schema hypothesis: every planner intent is a
required output property, and each property's quote enum contains only sources
valid for that intent. V4 remains frozen rather than silently modified.

The V5 cohort achieved 100% API success, schema validity, answer correctness,
document/family coverage, citation grounding, and citation precision. One case
scored `unsupported_policy_claims_empty = false` because its summary changed
"causal benefit cannot be inferred" into "no causal benefit." That is a genuine
unsupported zero-effect claim, not a label problem.

V6 freezes V5 and tests one final calibration hypothesis: explicitly distinguish
unknown causal effect from proven zero effect while preserving every V5 gain.

The V6 cohort passed every gate:

```text
API and schema validity             = 100%
answer correctness                  = 100%
expected document/family citation   = 100%
citation resolution and precision   = 100%
unsupported claims empty            = 100%
reasoning tokens                     = 0
```

The V5-to-V6 comparison contains one improvement, the prior causal-language
failure, and zero regressions. V6 is therefore authorized for the frozen full
100-question run.

## Setup

Install dependencies and start the existing pgvector database:

```bash
python -m pip install -r requirements-commit07.txt
docker compose -f docker-compose.commit06.yml up -d
```

The Commit 06 vector volume is preserved. If the index is missing, rebuild it:

```bash
python -m src.retrieval.build_vector_index --recreate
```

## Step 1 - Local tests

```bash
python -m unittest discover -s tests/commit07 -v
```

These tests cover:

- expansion from 50 customers to 100 questions,
- no-warning policy planning with consent constraints,
- vector-query embedding caching,
- bounded authoritative context construction,
- exact citation excerpt validation.

## Step 2 - Retrieval gate

Run retrieval and context construction without calling the generation model:

```bash
python -m evals.commit07.retrieval_gate \
  --database data/warehouse/signaldesk.duckdb \
  --report evals/commit07/reports/retrieval_gate_v4.json
```

Do not run generation if this gate is below 90%. Review
`evals/commit07/reports/retrieval_gate.json` first.

## Step 3 - Targeted V6 calibration test

```bash
python -m evals.commit07.runner \
  --database data/warehouse/signaldesk.duckdb \
  --case-ids-file evals/commit07/v4_failure_cohort.txt \
  --output evals/commit07/reports/v6_failure_cohort_results.jsonl

python -m evals.commit07.metrics \
  --results evals/commit07/reports/v6_failure_cohort_results.jsonl \
  --report evals/commit07/reports/v6_failure_cohort_report.json
```

The runner fixes:

```text
model = gpt-5.6-luna
reasoning = none
```

The ten cases represent the distinct V3 failure modes, the two V4 coverage
failures, and the V5 causal-language failure. This is a focused hypothesis test,
not the adoption measurement. Do not tune labels or remove near-duplicate
documents based on its result.

## Step 4 - Full 100-question run

```bash
python -m evals.commit07.runner \
  --database data/warehouse/signaldesk.duckdb \
  --output evals/commit07/reports/rag_v6_results.jsonl

python -m evals.commit07.metrics \
  --results evals/commit07/reports/rag_v6_results.jsonl \
  --report evals/commit07/reports/rag_v6_report.json

python -m evals.commit07.compare \
  --baseline evals/commit07/reports/rag_v1_results.jsonl \
  --candidate evals/commit07/reports/rag_v6_results.jsonl \
  --output evals/commit07/reports/compare_v3_vs_v6.json
```

The report separates:

- retrieval latency,
- generation latency,
- total latency,
- input, cached-input, output, and reasoning tokens,
- estimated generation cost,
- risk and evidence correctness,
- citation and unsupported-claim behavior,
- failures by question type.

API retries are bounded to three attempts for transient timeout, connection,
rate-limit, server, and incomplete-response errors. Generation has an explicit
3,000-token output budget. Reports keep first-attempt success separate from
eventual success so retries improve reliability without hiding instability.

## Full 100-question result and adoption

The final V6 run passed the live retrieval gate and every precommitted generation
target:

| Metric | Target | V3 baseline | V6 | Decision |
|---|---:|---:|---:|---|
| Retrieval gate | >=90% | 100% | 100% | Pass |
| API success | 100% | 98% | 100% | Pass |
| Schema validity | 100% | 98% | 100% | Pass |
| Risk correctness | 100% | 100% of 98 | 100% | Pass |
| Answer correctness | >=95% | 100% of 98 | 100% | Pass |
| Citation document grounding | 100% | 100% of 98 | 100% | Pass |
| Exact citation excerpts | 100% | 83.67% case rate | 100% | Pass |
| Expected policy-family citation | >=90% | 75.51% | 100% | Pass |
| Unsupported claims empty | >=95% | 97.96% | 100% | Pass |
| Reasoning tokens | 0 | 0 | 0 | Pass |

The 100-case comparison reports no regressions. V6 improved 18 exact-excerpt
cases, 10 expected-document-citation cases, and 26 expected-family-citation
cases. Both V3 timeout cases completed in V6.

V6 also reduced mean total latency from 6.6944 to 5.5025 seconds and estimated
cost per successful response from `$0.007745` to `$0.006378`. Input tokens per
response increased from about 3,891 to 4,945 because intent-keyed schemas carry
more structure; output tokens fell from about 825 to 558.

V6 is adopted for Commit 07.

### Residual limitation

Exact quote identity is deterministic, but the current metrics do not prove
semantic entailment between every cited quote and every generated prose clause.
A manual audit found nine policy-guardrail summaries that conservatively state
causal benefit is "not established" without a retrieved governance source. This
is not the V5 zero-effect failure, but future evaluation should distinguish
"the retrieved context does not establish" from a global knowledge claim.

One summary was 304 characters despite the soft under-300 prompt instruction;
it remained below the 500-character schema limit and was coherent. No duplicate
quote IDs or unexpected non-ASCII output appeared in the full run.

## Definition of done

Commit 07 is complete when:

- 100 questions are frozen,
- the retrieval gate is measured,
- the strict structured output succeeds on the full run,
- retrieval and generation metrics remain separate,
- each citation is linked to a retrieved document and exact excerpt,
- failures are classified without post-hoc label changes,
- Learning Log and Blog 07 contain the measured result,
- the system remains recommendation-only with human review.
