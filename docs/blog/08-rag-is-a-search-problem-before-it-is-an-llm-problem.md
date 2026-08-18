# RAG Is a Search Problem Before It Is an LLM Problem

Commit 07 connected policy retrieval to a structured LLM response. It ended
with a result that looked strong:

```text
100 frozen questions
100% expected policy-family retrieval
100% exact citation grounding
100% answer correctness
```

That did not prove the retriever was optimal.

It proved that one bounded Customer 360 workflow worked with one retrieval
configuration. Commit 08 stepped backward from generation and asked a more
basic question:

> Which search decisions actually improve retrieval, and which merely make the
> system different?

That distinction matters because a RAG failure can occur on either side of the
context boundary:

```text
retrieval failure
  required evidence never reaches the model

generation failure
  evidence reaches the model, but the answer misuses or ignores it
```

A prompt change cannot reliably repair missing context. A retriever change
cannot repair unsupported prose when the right evidence was already present.

## Freeze the inputs first

I reused the 50 curated Commit 06 policy queries. Each query has one or more
relevance selectors defined by policy family and topic. The knowledge corpus
contains 1,004 documents represented by 1,003 source files.

Both inputs are pinned by SHA-256:

```text
retrieval cases = b1024f1a...
knowledge corpus = f5cc6746...
```

The experiment exits before an API or database call when either fingerprint
changes. Without that boundary, a corpus correction or label edit could look
like an algorithmic improvement.

The embedding boundary also remains fixed:

```text
model      = text-embedding-3-small
dimensions = 1536
```

## Correct the metric before comparing systems

The Commit 06 benchmark called this metric Recall@K:

> Percentage of queries with at least one curated relevant document in the top
> K results.

That is useful, but its precise name is hit rate@K. Recall normally measures
the fraction of all relevant items recovered.

Commit 08 retains the historical number and adds complete selector coverage.
The difference appears in a cross-family question that requires both campaign
suppression and consent suppression:

```text
one relevant family found  -> hit
only one of two found       -> incomplete selector coverage
```

The lexical reference reaches 82% hit rate at rank ten but only 80% complete
selector coverage. A single score would hide the partial failure.

## The matrix

I compared eight configurations:

```text
lexical reference
vector without metadata filters
vector baseline with 220/40 chunks
vector with 120/20 chunks
vector with 220/0 chunks
vector with 400/60 chunks
vector plus lexical reciprocal-rank fusion
lexical reranking of vector candidates
```

The baseline retrieves only current, approved policy documents. The unfiltered
treatment intentionally removes that protection. Each chunk configuration uses
an isolated pgvector table so the adopted Commit 07 index remains unchanged.

## The measured result

| Experiment | Hit@5 | Selectors@5 | MRR | p95 ms |
|---|---:|---:|---:|---:|
| lexical | 68% | 68% | 0.4974 | 7.920 |
| vector unfiltered | 68% | 96% | 0.3908 | 33.407 |
| vector baseline | 98% | 96% | 0.9032 | 24.050 |
| small chunks | 96% | 94% | 0.8944 | 24.625 |
| no overlap | 98% | 96% | 0.9032 | 21.579 |
| large chunks | 96% | 94% | 0.8957 | 28.856 |
| hybrid RRF | 88% | 86% | 0.7482 | 26.971 |
| lexical rerank | 94% | 92% | 0.9007 | 26.661 |

At first glance, no overlap appears to win because its p95 is lower than the
baseline. That conclusion is wrong.

## Nominal parameters are not effective treatments

The `220/0` and `220/40` chunk configurations produced exactly the same 1,093
chunks. Their embedding text is byte-identical and both consumed 300,972 input
tokens.

Overlap is used only when a Markdown section exceeds the per-chunk content
budget. In this corpus, the extra chunks came from packing normal sections, not
splitting an oversized section. Changing the overlap parameter therefore did
nothing.

The two indexes produced the same aggregate retrieval quality. A few low-ranked
ties changed order across separate embedding/index builds, but no evaluated
case changed. The observed latency difference is ordinary run variation between
equivalent treatments.

This was also an avoidable cost. Building the duplicate index consumed 300,972
embedding input tokens.

The harness now fingerprints effective chunk content and the complete retrieval
treatment. An equivalent treatment cannot become an adoption candidate merely
because one timing sample is lower.

The lesson generalizes beyond chunking:

> Compare the inputs that actually reach a model or algorithm, not only the
> configuration labels used to produce them.

## Metadata filters are part of correctness

The unfiltered vector experiment has 96% selector coverage at rank five, equal
to the filtered baseline. That number is dangerously incomplete.

Only 26.4% of its first five results are both current and approved.

The corpus deliberately includes drafts, superseded policies, incomplete
material, and reference documents. Many share the same family and topic as the
approved policy. They are semantically relevant but operationally invalid.

```text
semantic relevance != authority
```

No similarity score can infer that a superseded rule must not control a current
customer decision. Status and authority are structured facts, so metadata
filters enforce them before ranking.

This is why governance is a hard gate rather than a weighted metric. Higher
relevance cannot compensate for using the wrong version of a policy.

## Smaller chunks were not more precise

Reducing the chunk configuration from `220/40` to `120/20` increased the index:

```text
1,093 chunks -> 2,042 chunks
```

It did not improve early ranking. Hit rate and selector coverage at five both
fell two points, and `refunds_05` regressed.

Smaller chunks often sound inherently more precise. They can also separate a
rule from the context that makes its embedding distinctive, create more near-
duplicate candidates, and increase index cost. The right size is an empirical
property of the documents and questions.

Large `400/60` chunks reduced the index to 1,004 chunks but also lost two points
at rank five and regressed `retention_03`. Fewer vectors did not produce a
better or faster measured result.

## Hybrid retrieval fixed one case and damaged six

Lexical search succeeded on `retention_02`, where vector search placed the
relevant retention policy at rank eight. Reciprocal-rank fusion moved it to
rank four.

That local improvement looked like a good reason to adopt hybrid retrieval.
The regression comparison rejected it:

```text
improved at rank five = 1 case
regressed at rank five = 6 cases
selector coverage@5 = 96% -> 86%
MRR = 0.9032 -> 0.7482
```

The generated policy corpus uses repeated operational vocabulary. The custom
lexical scorer overweights some common phrases that vector similarity handles
better. Equal reciprocal-rank fusion gives that weaker ranking too much global
influence.

Lexical reranking was less damaging, but still caused two regressions and did
not fix the persistent failures. A technique being popular does not make its
default weighting correct for a particular corpus.

## Two failures, two diagnoses

The baseline misses complete selector coverage at rank five for two cases.

### `retention_02`: ranking ambiguity

The correct document is present at rank eight. Semantically similar offer and
retention documents occupy the first positions. Increasing K finds it, while a
global lexical correction creates more regressions than improvements.

This is a ranking problem.

### `cross_family_01`: query decomposition

Every strategy covers only one of two required policy intents, even at rank
ten. More chunks, larger K, fusion, and reranking all fail to recover the second
intent.

This is not primarily a ranking problem. A single query underrepresents one
side of a compound information need.

The next retrieval hypothesis is explicit multi-intent decomposition:

```text
compound question
  -> intent A query
  -> intent B query
  -> retrieve each independently
  -> merge with intent coverage constraints
```

Commit 07 already uses this pattern inside its bounded Customer 360 policy
planner and passed its 100-question retrieval gate. Generalizing it should use
a new set of frozen multi-intent questions. Tuning against one known failure
would demonstrate memorization of the benchmark, not a general solution.

## The correct decision was no change

No distinct treatment improved the vector baseline without a governance failure
or retrieval regression. The baseline remains adopted.

I did not rerun the 100-question LLM evaluation. The generation model, prompt,
and retrieval treatment would be unchanged, so that run would measure
repeatability rather than a new hypothesis.

This negative result is the point of the harness:

```text
no proven retrieval improvement
  -> no production change
  -> no unnecessary generation experiment
```

RAG engineering is not a sequence of adding techniques until the architecture
looks sophisticated. It is the discipline of locating the failing boundary,
changing one effective treatment, measuring both gains and regressions, and
keeping the existing system when the evidence does not justify a change.
