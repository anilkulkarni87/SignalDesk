# SignalDesk Commit 08 - Retrieval Experiments

Commit 08 asks a narrower question than Commit 07:

> When a grounded answer fails, did retrieval fail to supply the right policy,
> or did generation fail to use policy that was already present?

Commit 07 froze the generation boundary at prompt V6. Commit 08 changes only
retrieval variables until one configuration earns an end-to-end generation
comparison.

This is still bounded RAG. It does not add model-selected tools, agents, or
automatic customer actions.

## Frozen inputs

The experiment contract is
`evals/commit08/experiment_contract.json`. It pins:

```text
50 Commit 06 retrieval cases
case SHA-256   = b1024f1a2429d29832a0c14f68f90c8cbe29e0234540f61f1a2c7f1fbb8ff659

1,003 corpus source files representing 1,004 knowledge documents
corpus SHA-256 = f5cc6746ea8b176e5656283b1d2ededc42ea8cdc3bdb5e076a85aa23dc86b639

embedding model      = text-embedding-3-small
embedding dimensions = 1536
evaluation ranks     = 1, 3, 5, 10
candidate pool       = 20 documents
```

The runner fails before making an API call if either fingerprint changes.
That prevents an input edit from masquerading as a retrieval improvement.

## Experiment matrix

| ID | Variable isolated | Hypothesis |
|---|---|---|
| `lexical_reference` | lexical-only reference | Exact policy terminology explains some vector misses. |
| `vector_unfiltered` | metadata filters off | Non-authoritative documents displace usable policy. |
| `vector_baseline` | Commit 07 baseline | `220/40`, vector-only, current and approved. |
| `vector_small_chunks` | `120/20` chunks | Smaller chunks improve topic focus at higher index cost. |
| `vector_no_overlap` | `220/0` chunks | Overlap can be removed without losing selector coverage. |
| `vector_large_chunks` | `400/60` chunks | Fewer chunks reduce index size but may dilute similarity. |
| `hybrid_rrf` | vector plus lexical | Rank fusion recovers complementary lexical and semantic hits. |
| `vector_lexical_rerank` | reranking | Lexical evidence improves order inside the vector candidate set. |

Four pgvector tables isolate the chunk configurations. They do not overwrite
the Commit 06/07 `knowledge_chunks` table.

## Metrics

The old benchmark called its any-relevant-document hit metric `Recall@K`.
Commit 08 keeps the historical value but names it precisely:

```text
hit rate@K
```

Commit 08 also adds:

```text
all-selector coverage@K
mean selector recall@K
mean document recall@K
precision@K
MRR
current-approved result rate@K
mean, p50, and p95 retrieval latency
per-case improvements and regressions versus vector_baseline
```

The selector metric matters for the cross-family case. Returning a campaign
suppression policy but omitting the consent suppression policy is an any-hit
success and a complete-selector failure.

Governance is a hard selection gate. A configuration cannot become a generation
candidate if its top-five results are not 100% current and approved, regardless
of its relevance score.

## Run the experiment

Install the existing dependency chain and start the Commit 06 pgvector service:

```bash
python -m pip install -r requirements-commit08.txt
docker compose -f docker-compose.commit06.yml up -d
```

Validate the frozen contract without using the API:

```bash
python -m evals.commit08.matrix --stage validate
```

With `OPENAI_API_KEY` available in the same terminal, build the four isolated
indexes and run all eight experiments:

```bash
python -m evals.commit08.matrix --stage all
```

The result is written to:

```text
evals/commit08/reports/retrieval_experiment_matrix.json
```

Index metadata is reused on later runs when the model, dimensions, corpus
fingerprint, and chunk settings match. Use `--rebuild` only when intentionally
repeating index construction.

Individual stages and experiments can be isolated:

```bash
python -m evals.commit08.matrix --stage build
python -m evals.commit08.matrix --stage benchmark
python -m evals.commit08.matrix \
  --stage benchmark \
  --experiment lexical_reference
```

## Measured result

The full matrix is preserved in
`evals/commit08/reports/retrieval_experiment_matrix.json`. The corrected
treatment analysis is in
`evals/commit08/reports/retrieval_experiment_analysis.json`.

| Experiment | Hit@5 | Selectors@5 | MRR | p95 ms | Decision |
|---|---:|---:|---:|---:|---|
| lexical reference | 68% | 68% | 0.4974 | 7.920 | reject: 15 regressions |
| vector unfiltered | 68% | 96% | 0.3908 | 33.407 | reject: only 26.4% current-approved at 5 |
| vector baseline | 98% | 96% | 0.9032 | 24.050 | retain |
| small chunks | 96% | 94% | 0.8944 | 24.625 | reject: `refunds_05` regression |
| no overlap | 98% | 96% | 0.9032 | 21.579 | not a distinct treatment |
| large chunks | 96% | 94% | 0.8957 | 28.856 | reject: `retention_03` regression |
| hybrid RRF | 88% | 86% | 0.7482 | 26.971 | reject: six regressions |
| lexical rerank | 94% | 92% | 0.9007 | 26.661 | reject: two regressions |

The result is a valid negative experiment: none of the tested alternatives
strictly improved the baseline without weakening governance or retrieval
coverage.

### Metadata filtering is a correctness boundary

The unfiltered vector treatment appears strong on family/topic selector
coverage, but only 26.4% of its first five results are both current and
approved. Draft, superseded, and reference documents share the same topics as
authoritative policies. Semantic similarity alone cannot decide which source
is allowed to control a customer recommendation.

### The overlap experiment was behaviorally empty

The `220/0` and `220/40` chunkers produced byte-identical embedding inputs:

```text
chunk count            = 1,093 for both
embedding input tokens = 300,972 for both
retrieval quality      = identical
```

The corpus sections fit inside the chunk budget, so the long-section overlap
path never executed. The lower p95 observed for `220/0` is timing noise, not an
improvement. Treatment fingerprints now prevent an equivalent configuration
from becoming an adoption candidate.

This also exposed avoidable experiment cost: 300,972 embedding tokens were used
to build the duplicate no-overlap index. Future experiments fingerprint
effective inputs before making paid API calls.

### Smaller, larger, hybrid, and reranked were worse

Small chunks doubled the index from 1,093 to 2,042 chunks and introduced a
`refunds_05` regression. Large chunks reduced the index to 1,004 chunks but
introduced a `retention_03` regression and increased p95 latency in this run.

Global hybrid retrieval fixed `retention_02`, moving its relevant policy from
rank eight to rank four, but caused six other rank-five selector regressions.
The improvement does not justify adopting the global fusion rule. Lexical
reranking also weakened two cases without fixing either persistent baseline
failure.

### Persistent failures

`retention_02` is a ranking ambiguity. The correct vector result exists at rank
eight, outside the five-document evaluation boundary. A global lexical fix is
too blunt because it damages stronger semantic rankings elsewhere.

`cross_family_01` is a query-decomposition failure. Every strategy retrieves
only one of its two required policy intents, even at rank ten. More results and
global fusion do not recover an intent that the single query underrepresents.

Commit 07 already decomposes its bounded Customer 360 workflow into explicit
policy intents and passed its 100-question retrieval gate. Generalizing that
approach should be tested later on a newly frozen multi-intent benchmark, not
tuned against this single cross-family case.

## Adoption decision

`vector_baseline` remains adopted. No new treatment earned the Commit 07
generation gate. Rerunning 100 LLM calls would repeat the existing pipeline
rather than test a new retrieval hypothesis, so Commit 08 does not spend those
calls.

This is the engineering decision the evaluation was designed to support:

```text
no proven retrieval improvement -> no production change -> no generation rerun
```

## Definition of done

Commit 08 is complete when:

- frozen inputs are fingerprinted,
- all eight retrieval experiments are measured,
- chunk count and index-build cost are recorded,
- retrieval quality and latency are compared separately,
- per-case improvements and regressions are reviewed,
- a strict candidate passes the frozen Commit 07 generation gate, or the
  baseline is retained with a measured negative result,
- the learning log and Blog 08 contain measured conclusions,
- no agent or automatic execution is introduced.

All conditions are satisfied. Commit 08 is complete.
