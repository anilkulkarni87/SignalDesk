#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import mean, median
from time import perf_counter

from src.retrieval.embeddings import DEFAULT_EMBEDDING_MODEL, OpenAIEmbedder
from src.retrieval.lexical import LexicalIndex
from src.retrieval.vector_store import PgVectorStore


RANKS = (1, 3, 5)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("evals/commit06/retrieval_cases.jsonl"),
    )
    parser.add_argument("--corpus-dir", default="data/generated/knowledge")
    parser.add_argument(
        "--retriever",
        choices=("lexical", "vector", "both"),
        default="lexical",
    )
    parser.add_argument("--dsn")
    parser.add_argument("--model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--dimensions", type=int)
    parser.add_argument("--embedding-batch-size", type=int, default=50)
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("evals/commit06/reports/retrieval_benchmark.json"),
    )
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return round(ordered[index], 3)


def score_case(case: dict, retrieved_ids: list[str], latency_ms: float) -> dict:
    relevant = set(case["relevant_document_ids"])
    first_rank = next(
        (rank for rank, document_id in enumerate(retrieved_ids, start=1)
         if document_id in relevant),
        None,
    )
    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "query": case["query"],
        "relevant_document_ids": sorted(relevant),
        "retrieved_document_ids": retrieved_ids,
        "first_relevant_rank": first_rank,
        "reciprocal_rank": round(1 / first_rank, 6) if first_rank else 0.0,
        "latency_ms": round(latency_ms, 3),
        **{
            f"recall_at_{rank}": bool(relevant & set(retrieved_ids[:rank]))
            for rank in RANKS
        },
    }


def summarize(name: str, case_reports: list[dict], **extra) -> dict:
    latencies = [case["latency_ms"] for case in case_reports]
    count = len(case_reports)
    return {
        "retriever": name,
        "cases": count,
        "metric_definition": (
            "Recall@K is the percentage of queries with at least one curated "
            "relevant document in the top K document-level results."
        ),
        **{
            f"recall_at_{rank}_pct": round(
                100 * sum(case[f"recall_at_{rank}"] for case in case_reports) / count,
                2,
            ) if count else 0.0
            for rank in RANKS
        },
        "mrr": round(mean(case["reciprocal_rank"] for case in case_reports), 4)
        if case_reports else 0.0,
        "latency_ms": {
            "mean": round(mean(latencies), 3) if latencies else 0.0,
            "p50": round(median(latencies), 3) if latencies else 0.0,
            "p95": percentile(latencies, 0.95),
        },
        **extra,
        "case_reports": case_reports,
    }


def run_lexical(cases: list[dict], corpus_dir: str) -> dict:
    index_started = perf_counter()
    statuses = set(cases[0]["statuses"])
    authorities = set(cases[0]["authorities"])
    index = LexicalIndex.from_corpus(
        corpus_dir,
        statuses=statuses,
        authority=authorities,
    )
    index_build_latency_ms = (perf_counter() - index_started) * 1000
    reports = []
    for case in cases:
        started = perf_counter()
        results = index.search(
            case["query"],
            top_k=max(RANKS),
        )
        latency_ms = (perf_counter() - started) * 1000
        reports.append(score_case(
            case,
            [result.document_id for result in results],
            latency_ms,
        ))
    return summarize(
        "lexical",
        reports,
        index_build_latency_ms=round(index_build_latency_ms, 3),
    )


def run_vector(
    cases: list[dict],
    *,
    dsn: str | None,
    model: str,
    dimensions: int | None,
    embedding_batch_size: int,
) -> dict:
    store = PgVectorStore(dsn)
    index_metadata = store.get_metadata()
    indexed_model = index_metadata.get("embedding_model")
    if indexed_model and indexed_model != model:
        raise ValueError(
            f"Vector index uses {indexed_model}, but benchmark requested {model}"
        )

    embedder = OpenAIEmbedder(
        model=model,
        dimensions=dimensions,
        batch_size=embedding_batch_size,
    )
    embedding_started = perf_counter()
    embedding_run = embedder.embed([case["query"] for case in cases])
    embedding_latency_ms = (perf_counter() - embedding_started) * 1000
    average_embedding_latency_ms = embedding_latency_ms / len(cases)

    reports = []
    search_latencies = []
    for case, query_vector in zip(cases, embedding_run.vectors):
        started = perf_counter()
        results = store.search(
            query_vector,
            top_k=max(RANKS),
            statuses=set(case["statuses"]),
            authorities=set(case["authorities"]),
        )
        search_latency_ms = (perf_counter() - started) * 1000
        search_latencies.append(search_latency_ms)
        reports.append(score_case(
            case,
            [result.document_id for result in results],
            search_latency_ms + average_embedding_latency_ms,
        ))

    return summarize(
        "vector",
        reports,
        embedding_model=embedding_run.model,
        embedding_dimensions=embedding_run.dimensions,
        embedding_input_tokens=embedding_run.input_tokens,
        embedding_batch_latency_ms=round(embedding_latency_ms, 3),
        vector_search_latency_ms={
            "mean": round(mean(search_latencies), 3),
            "p50": round(median(search_latencies), 3),
            "p95": percentile(search_latencies, 0.95),
        },
        index_metadata=index_metadata,
    )


def main():
    args = parse_args()
    cases = read_jsonl(args.cases)
    if len(cases) != 50:
        raise ValueError(f"Expected 50 frozen retrieval cases, found {len(cases)}")

    retrievers = {}
    if args.retriever in {"lexical", "both"}:
        retrievers["lexical"] = run_lexical(cases, args.corpus_dir)
    if args.retriever in {"vector", "both"}:
        retrievers["vector"] = run_vector(
            cases,
            dsn=args.dsn,
            model=args.model,
            dimensions=args.dimensions,
            embedding_batch_size=args.embedding_batch_size,
        )

    report = {
        "cases_file": str(args.cases),
        "corpus_dir": args.corpus_dir,
        "cases": len(cases),
        "retrievers": retrievers,
    }
    if "lexical" in retrievers and "vector" in retrievers:
        report["comparison"] = {
            f"vector_minus_lexical_recall_at_{rank}_pct": round(
                retrievers["vector"][f"recall_at_{rank}_pct"]
                - retrievers["lexical"][f"recall_at_{rank}_pct"],
                2,
            )
            for rank in RANKS
        }
        report["comparison"]["vector_minus_lexical_mrr"] = round(
            retrievers["vector"]["mrr"] - retrievers["lexical"]["mrr"],
            4,
        )

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    console_report = {
        "cases_file": report["cases_file"],
        "cases": report["cases"],
        "report": str(args.report),
        "retrievers": {
            name: {
                key: value
                for key, value in result.items()
                if key != "case_reports"
            }
            for name, result in retrievers.items()
        },
    }
    if "comparison" in report:
        console_report["comparison"] = report["comparison"]
    print(json.dumps(console_report, indent=2))


if __name__ == "__main__":
    main()
