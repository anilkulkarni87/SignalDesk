# Lesson 06 - Retrieval from First Principles

> Learning scope: retrieval judgments and the knowledge corpus are curated and
> synthetic. Benchmark success does not prove quality on natural user queries.

## Outcome

You will be able to compare lexical and vector retrieval using Recall@K, MRR,
latency, and operational constraints rather than choosing from intuition.

## Problem

An LLM cannot ground policy advice in a document it never receives. Before RAG
is a generation problem, it is a search problem: did the retriever place a
relevant, current, approved document inside the context budget?

## First principles

For each frozen query:

```text
Recall@K = did at least one curated relevant document appear in the top K?
MRR      = average reciprocal rank of the first relevant document
latency  = time required to produce the ranked result
```

Recall@K measures discovery within a budget. MRR rewards placing the first
relevant result earlier. Neither evaluates whether the model later cites or
interprets the document correctly.

## Build

Inspect:

- [Retrieval cases](../../../../evals/commit06/retrieval_cases.jsonl)
- [Benchmark report](../../../../evals/commit06/reports/retrieval_benchmark.json)
- [Commit 06 guide](../../../../README_COMMIT06.md)

Pick one query where lexical retrieval fails at rank five and inspect the
relevant document wording. Explain why token overlap is insufficient.

## Measure

Predict the quality and latency winner before reading the comparison:

| Retriever | Recall@5 | MRR | P95 query latency |
|---|---:|---:|---:|
| Lexical | 68% | 0.4697 | 5.129 ms |
| Vector | 98% | 0.9007 | 40.470 ms |

The experiment supports a vector quality advantage on these 50 queries. It does
not force vector infrastructure into every later serving path.

## Break

Challenge the result:

- Were relevance judgments independent from corpus generation?
- Would natural analyst phrasing preserve the vector advantage?
- What happens when effective dates and approval status change?
- Is the latency comparison warm, cold, local, or networked?
- Does a relevant family count when the exact expected document is absent?

## Explain

Answer in your own words:

1. Why does Recall@5 differ from citation correctness?
2. Why can the best offline retriever remain outside the accepted product path?
3. Which new evidence would justify changing the serving retriever?

## Ship

Keep a retrieval decision record containing corpus version, frozen queries,
relevance labels, quality, latency, cost, and the accepted serving decision.

## Verify

```bash
python run_course.py check 06
```

The command validates frozen metrics and runs the deterministic Commit 06 tests.

## Continue

The full curriculum will add grounded RAG and retrieval experiments as Lessons
07 and 08. The pilot path continues to agents:

```bash
python run_course.py start 10
```

Deep reading: [Vector Search from First Principles](../../../../docs/blog/06-vector-search-from-first-principles-for-data-engineers.md).

