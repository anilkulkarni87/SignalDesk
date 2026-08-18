# SignalDesk Commit 06 - Embeddings and Vector Search

Commit 06 implements the roadmap's second conceptual jump:

```text
generation -> retrieval
```

The LLM can reason over supplied context, but it cannot be expected to know
NovaCart's private policies. This commit builds and measures the retrieval layer
that will supply that context in Commit 07.

No agent, action tool, or answer-generation workflow is introduced here.

## Learning objective

Build vector retrieval without a RAG framework:

```text
generated knowledge document
  -> metadata-aware chunking
  -> OpenAI embedding
  -> pgvector
  -> cosine similarity search
  -> document-level ranking metrics
```

The existing lexical retriever remains the control experiment. Commit 06 asks a
specific question:

> Does semantic vector retrieval find the correct current, approved NovaCart
> knowledge more reliably than the lexical baseline on the same 50 queries?

## Corpus

The source is `data/generated/knowledge`, created by
`data/knowledge/generate_knowledge_docs_v2.py`.

The loader currently exposes:

- 1,000 generated Markdown documents,
- 4 explicit known-knowledge-gap records,
- 9 business knowledge families plus governance gaps,
- current, superseded, draft, and incomplete material,
- approved and reference authority levels.

All documents enter the vector index. Query-time metadata filters restrict normal
retrieval to `CURRENT` and `APPROVED` sources. This preserves stale documents for
freshness testing instead of hiding them during ingestion.

## Chunking

`src/retrieval/chunking.py` parses Markdown sections and packs adjacent sections
into chunks of at most 220 whitespace-delimited words. Long sections use a
40-word overlap.

Each embedding input contains:

- document title,
- family,
- topic,
- document type,
- section names,
- chunk content.

With the current generated corpus, this produces:

```text
1,004 documents -> 1,093 chunks
```

The chunk size and overlap are intentionally fixed for this baseline. Commit 08
will vary them experimentally.

## Frozen retrieval cases

`evals/commit06/retrieval_cases.jsonl` contains 50 queries:

- 5 topics for each of the 9 business knowledge families,
- 4 known-gap queries,
- 1 cross-family campaign/consent query.

Every case freezes the set of current approved document IDs selected by corpus
family and topic. Multiple documents can be relevant because the synthetic
corpus deliberately contains overlapping policies.

For this experiment, Recall@K means:

> Percentage of queries with at least one curated relevant document in the top K
> document-level results.

MRR uses the rank of the first relevant document. Chunk results are deduplicated
to documents before scoring.

Regenerate the cases only when the generated corpus intentionally changes:

```bash
python -m evals.commit06.make_retrieval_cases
```

## Local setup

Install the Commit 06 dependencies:

```bash
python -m pip install -r requirements-commit06.txt
```

Start PostgreSQL with pgvector:

```bash
docker compose -f docker-compose.commit06.yml up -d
```

The default local connection is:

```text
postgresql://signaldesk:signaldesk@localhost:5432/signaldesk
```

Override it with `SIGNALDESK_PG_DSN` or the command-line `--dsn` option.

## Step 1 - Reproduce the lexical baseline

```bash
python -m evals.commit06.retrieval_benchmark \
  --retriever lexical \
  --report evals/commit06/reports/retrieval_benchmark_lexical.json
```

Measured baseline on the frozen 50 cases:

| Metric | Lexical |
|---|---:|
| Recall@1 | 36.0% |
| Recall@3 | 58.0% |
| Recall@5 | 68.0% |
| MRR | 0.4697 |
| Mean query latency | 4.312 ms |
| One-time index build | 83.605 ms |

This is a useful baseline because it fails on paraphrases such as semantic
descriptions of consent timestamps, declining purchases, and knowledge gaps.

## Step 2 - Build the vector index

The embedding model is `text-embedding-3-small`. This is separate from the
`gpt-5.6-luna` generation model used in Commit 05 and the future Commit 07 RAG
evaluation.

Make `OPENAI_API_KEY` available in the terminal, then run:

```bash
python -m src.retrieval.build_vector_index --recreate
```

This command:

1. loads all generated knowledge,
2. creates 1,093 chunks,
3. embeds them in batches,
4. creates the pgvector schema,
5. upserts the chunks and vectors,
6. creates an HNSW cosine index,
7. records model, dimension, token, and latency metadata.

The report is written to:

```text
evals/commit06/reports/vector_index_manifest.json
```

`--recreate` replaces only the local `knowledge_chunks` table. It does not touch
the DuckDB warehouse or generated source documents.

## Step 3 - Compare lexical and vector retrieval

```bash
python -m evals.commit06.retrieval_benchmark \
  --retriever both \
  --report evals/commit06/reports/retrieval_benchmark.json
```

The comparison report includes:

- Recall@1,
- Recall@3,
- Recall@5,
- MRR,
- mean, p50, and p95 latency,
- per-case rankings and misses,
- vector-minus-lexical metric deltas,
- embedding model, dimensions, and input-token usage.

The roadmap target was:

```text
Vector Recall@5 > 85%
```

Measured comparison:

| Metric | Lexical | Vector | Delta |
|---|---:|---:|---:|
| Recall@1 | 36.0% | 86.0% | +50.0 points |
| Recall@3 | 58.0% | 92.0% | +34.0 points |
| Recall@5 | 68.0% | 98.0% | +30.0 points |
| MRR | 0.4697 | 0.9007 | +0.4310 |
| Mean end-to-end query latency | 4.312 ms | 35.480 ms | +31.168 ms |

Vector database search alone averaged 12.120 ms. The remaining end-to-end vector
latency came primarily from embedding the query. The corpus index used 300,972
embedding input tokens and took 18.305 seconds to build end to end.

The vector retriever found at least one relevant document in the top five for 49
of 50 cases, exceeding the target by 13 percentage points. The one miss was
`retention_02`. Its query asked what evidence should be reviewed before a save
incentive. Vector search ranked current approved offer-eligibility policies above
the frozen retention decision-framework documents. This is an adjacent-family
ranking error and a useful Commit 08 hypothesis.

The labels and inputs remain unchanged after measurement.

## Step 4 - Inspect one vector query

```bash
python -m src.retrieval.vector_search \
  "How long should we wait after a customer already received an incentive?" \
  --top-k 5
```

Normal search filters to current approved sources. Use
`--include-non-authoritative` only when deliberately inspecting stale-source
behavior.

## Existing policy-grounding work

An early policy-grounded prompt, output schema, customer query planner, and
25-case model run were built during exploration. That work remains valuable, but
under the roadmap it is Commit 07 groundwork because it performs
retrieval-augmented generation. It is intentionally carried forward on the
Commit 07 branch instead of being included in the Commit 06 implementation.

Commit 06 must first prove retrieval quality independently. This prevents a good
LLM answer from hiding a weak retriever.

The generation configuration remains unchanged for that later work:

```text
model = gpt-5.6-luna
reasoning = none
```

## Verification without an API key

Run the local automated tests:

```bash
python -m unittest discover -s tests/commit06 -v
```

They validate:

- metadata-preserving chunking,
- chunk-size constraints,
- exactly 50 grounded retrieval cases,
- Recall@K and reciprocal-rank calculation,
- pgvector literal validation.

The pgvector integration has also been tested with synthetic vectors for schema
creation, upsert, current/approved filtering, document deduplication, HNSW index
creation, and cosine ranking.

## Definition of done

Commit 06 is complete. The final report demonstrates that all of the following
are true:

- generated knowledge corpus validation passes,
- 50 retrieval cases are frozen,
- lexical baseline is reproducible,
- document chunking is deterministic,
- real embeddings are stored in pgvector,
- HNSW cosine search returns document-level results,
- Recall@1, Recall@3, Recall@5, MRR, and latency are reported,
- vector and lexical results are compared on identical inputs,
- vector Recall@5 exceeds 85% or a measured failure hypothesis is documented,
- Learning Log and Blog 06 explain the measured result and tradeoffs.

Stop the local database when finished:

```bash
docker compose -f docker-compose.commit06.yml down
```

Do not add `-v` unless the vector index should also be deleted.
