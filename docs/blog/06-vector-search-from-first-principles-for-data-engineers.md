# Vector Search From First Principles for Data Engineers

After building an LLM regression suite, it was tempting to connect a vector
database to the prompt and call the result RAG.

I deliberately stopped one layer earlier.

Before an LLM can answer from private business knowledge, the retrieval system
must prove that it can find the right knowledge. Otherwise, a fluent model answer
can hide a weak search system.

SignalDesk Commit 06 therefore asks one bounded question:

> Can semantic vector retrieval find the correct current NovaCart policies more
> reliably than lexical search on the same 50 queries?

No agent was added. No action was executed. The generation model was not called.

## Why Customer 360 is not enough

SignalDesk already had a deterministic Customer 360 layer containing facts such
as purchase decline, engagement decline, consent, subscription cancellation, and
open support attention.

Those tables should own customer facts. They should not become a storage format
for every policy, playbook, procedure, exception, and known organizational gap.

The generated NovaCart knowledge corpus contains that second kind of context:

- retention decision guidance,
- offer rules,
- support playbooks,
- shipping and refund policies,
- loyalty guidance,
- campaign rules,
- subscription procedures,
- consent constraints,
- explicit known knowledge gaps.

It also contains stale, draft, incomplete, and non-authoritative material. That
messiness is important because enterprise retrieval is not only about semantic
similarity. It is also about source control.

## The pipeline

I implemented the retrieval path without a RAG framework:

```text
Markdown document
  -> parse metadata
  -> split and pack sections
  -> create embedding input
  -> request embedding
  -> store vector in PostgreSQL
  -> HNSW cosine search
  -> filter current approved sources
  -> deduplicate chunks to documents
  -> calculate retrieval metrics
```

Building these steps directly made each contract visible.

## Chunking with document context

The loader produces 1,004 retrievable records: 1,000 generated Markdown
documents and 4 explicit knowledge gaps.

The chunker parses Markdown sections and packs adjacent sections into chunks of
at most 220 words. A long section uses a 40-word overlap. The current corpus
produces 1,093 chunks.

Every embedding input repeats the document context needed to interpret the
chunk:

```text
document title
knowledge family
document topic
document type
section names
chunk content
```

Without that context, a generic sentence about eligibility or escalation could
be difficult to distinguish from similar wording in another policy family.

The 220/40 settings are a baseline, not an optimized truth. Chunk-size and
overlap experiments belong to Commit 08.

## Embeddings and pgvector

The implementation uses `text-embedding-3-small`, producing 1,536-dimensional
vectors. PostgreSQL stores the vectors with pgvector and uses an HNSW index with
cosine distance.

All source documents enter the index, including superseded, draft, and incomplete
ones. Normal queries apply these filters:

```text
status    = CURRENT
authority = APPROVED
```

This distinction matters. Removing stale documents before indexing would make a
freshness test impossible. Keeping them indexed lets the query layer prove that
it applies source policy correctly.

The initial index build measured:

```text
documents              1,004
chunks                  1,093
embedding input tokens  300,972
embedding latency       15.150 seconds
total build time         18.305 seconds
```

## A frozen 50-query evaluation set

The evaluation set contains:

- 5 queries for each of 9 knowledge families,
- 4 known-gap queries,
- 1 cross-family campaign and consent query.

Each query has a frozen set of relevant current approved document IDs selected
from the corpus family and topic metadata.

Multiple documents can be relevant. The generated corpus intentionally contains
overlapping policies, so arbitrarily selecting one document as the only correct
answer would create a misleading test.

For this experiment, Recall@K means the percentage of queries that return at
least one relevant document in the top K document-level results. MRR measures the
rank of the first relevant document.

The inputs were frozen before the vector run and were not relabeled afterward.

## Establishing a lexical baseline

The existing lexical retriever uses token matching, inverse document frequency,
title weighting, and a small synonym map.

Its result was:

| Metric | Lexical |
|---|---:|
| Recall@1 | 36.0% |
| Recall@3 | 58.0% |
| Recall@5 | 68.0% |
| MRR | 0.4697 |
| Mean query latency | 4.312 ms |

Lexical search was fast, but paraphrases exposed its limit. Queries about a
withdrawn text-message permission, causal discount impact, or weakening customer
activity did not always share enough exact vocabulary with their target
documents.

## Vector search result

The vector run used the same corpus filters, queries, relevance labels, and top-K
measurement:

| Metric | Lexical | Vector | Change |
|---|---:|---:|---:|
| Recall@1 | 36.0% | 86.0% | +50.0 points |
| Recall@3 | 58.0% | 92.0% | +34.0 points |
| Recall@5 | 68.0% | 98.0% | +30.0 points |
| MRR | 0.4697 | 0.9007 | +0.4310 |

The roadmap target was Recall@5 above 85%. Vector retrieval reached 98%, finding
a relevant document in the top five for 49 of 50 cases.

The improvement was not free:

| Latency | Lexical | Vector |
|---|---:|---:|
| Mean end to end | 4.312 ms | 35.480 ms |
| p95 end to end | 5.129 ms | 40.470 ms |
| Vector database search only | n/a | 12.120 ms mean |

The vector end-to-end measurement includes query embedding. For the current
human investigation workflow, the added tens of milliseconds are small relative
to a workflow measured in minutes. At production traffic, that conclusion would
need concurrency, caching, and cost measurements.

## The useful 2%

The one miss was not random.

The query asked:

```text
What evidence should be reviewed before considering a customer save incentive?
```

The frozen relevant documents belonged to the retention family and explained
how to decide whether a retention intervention should be considered.

Vector search instead returned five current approved offer-family policies about
eligibility, exclusions, margin protection, and cooling periods.

The system confused two adjacent questions:

```text
Should a retention intervention be considered?
Is a particular offer allowed under policy?
```

That is a genuine retrieval boundary. I did not change the label to turn 98% into
100%.

A later experiment can test family-aware hybrid ranking, query decomposition, or
metadata filtering. Each option has a tradeoff: a strict family filter might fix
this case while damaging questions that correctly require multiple families.

## What this commit proves

Commit 06 proves that, for this generated corpus and frozen evaluation set:

- vector search handles semantic paraphrases substantially better than the
  lexical baseline,
- current and approved metadata filters can remain explicit,
- retrieval quality can be measured independently of generation quality,
- per-case review still matters after a strong aggregate score,
- semantic search introduces a measurable latency tradeoff.

It does not prove answer correctness, citation correctness, real-world policy
correctness, production scalability, or agent behavior.

Those boundaries are the point.

## What comes next

Commit 07 will connect this measured retrieval layer to the policy-grounded
generation work that was prototyped early. The model remains:

```text
gpt-5.6-luna
reasoning = none
```

The next evaluation must keep retrieval and generation metrics separate:

```text
Was relevant evidence retrieved?
Was the answer correct?
Were citations correct?
Were unsupported policy claims avoided?
What latency, token usage, and cost were added?
```

That is the progression from vector search to RAG: first prove that the system
can find the right context, then prove that the model uses it correctly.
