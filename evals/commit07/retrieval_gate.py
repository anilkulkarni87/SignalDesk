#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import mean, median
from time import perf_counter

from src.llm.customer_store import CustomerStore
from src.llm.policy_context import build_policy_context
from src.retrieval.embeddings import DEFAULT_EMBEDDING_MODEL, OpenAIEmbedder
from src.retrieval.query_planner import (
    VectorPolicyRetriever,
    plan_policy_queries,
)
from src.retrieval.vector_store import PgVectorStore


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("evals/commit07/cases.jsonl"),
    )
    parser.add_argument("--dsn")
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--embedding-dimensions", type=int)
    parser.add_argument("--per-query-top-k", type=int, default=3)
    parser.add_argument("--max-results", type=int, default=12)
    parser.add_argument("--max-context-characters", type=int, default=16_000)
    parser.add_argument("--min-pass-rate", type=float, default=90.0)
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("evals/commit07/reports/retrieval_gate.json"),
    )
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def pct(numerator: int, denominator: int) -> float:
    return round(100 * numerator / denominator, 2) if denominator else 0.0


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return round(ordered[index], 3)


def main():
    args = parse_args()
    cases = read_jsonl(args.cases)
    if len(cases) != 100:
        raise ValueError(f"Expected 100 frozen RAG questions, found {len(cases)}")

    customer_store = CustomerStore(args.database)
    retriever = VectorPolicyRetriever(
        embedder=OpenAIEmbedder(
            model=args.embedding_model,
            dimensions=args.embedding_dimensions,
        ),
        vector_store=PgVectorStore(args.dsn),
        per_query_top_k=args.per_query_top_k,
        max_results=args.max_results,
    )
    case_reports = []

    for case in cases:
        snapshot = customer_store.get_snapshot(case["customer_id"])
        planned_queries = plan_policy_queries(snapshot)
        started = perf_counter()
        results = retriever.retrieve(snapshot)
        latency_ms = (perf_counter() - started) * 1000
        context = build_policy_context(
            results,
            planned_queries=planned_queries,
            max_characters=args.max_context_characters,
        )

        retrieved_ids = {result.document_id for result in results}
        retrieved_families = {result.family for result in results}
        context_ids = set(context.document_ids)
        context_families = {
            result.family for result in context.included_results
        }
        expected_ids = set(case["expected_policy_doc_ids_all"])
        expected_families = set(case["expected_policy_families_all"])
        frozen_queries = case["planned_policy_queries"]
        current_queries = [query.to_dict() for query in planned_queries]

        case_report = {
            "case_id": case["case_id"],
            "customer_id": case["customer_id"],
            "question_type": case["question_type"],
            "retrieved_document_ids": [
                result.document_id for result in results
            ],
            "context_document_ids": context.document_ids,
            "retrieved_families": sorted(retrieved_families),
            "context_families": sorted(context_families),
            "expected_document_ids": sorted(expected_ids),
            "expected_families": sorted(expected_families),
            "planner_matches_frozen_input": current_queries == frozen_queries,
            "expected_documents_retrieved": expected_ids.issubset(retrieved_ids),
            "expected_families_retrieved": expected_families.issubset(
                retrieved_families
            ),
            "expected_documents_in_context": expected_ids.issubset(context_ids),
            "expected_families_in_context": expected_families.issubset(
                context_families
            ),
            "sources_current": all(
                result.status == "CURRENT" for result in results
            ),
            "sources_approved": all(
                result.authority == "APPROVED" for result in results
            ),
            "content_present": all(result.content.strip() for result in results),
            "policy_intents_have_quotes": all(
                context.intent_quote_ids.values()
            ),
            "intent_quote_counts": {
                intent_id: len(quote_ids)
                for intent_id, quote_ids in context.intent_quote_ids.items()
            },
            "context_characters": context.character_count,
            "context_quote_count": len(context.quotes_by_id),
            "latency_ms": round(latency_ms, 3),
        }
        case_report["passed"] = all([
            case_report["planner_matches_frozen_input"],
            case_report["expected_documents_retrieved"],
            case_report["expected_families_retrieved"],
            case_report["expected_documents_in_context"],
            case_report["expected_families_in_context"],
            case_report["sources_current"],
            case_report["sources_approved"],
            case_report["content_present"],
            case_report["policy_intents_have_quotes"],
        ])
        case_reports.append(case_report)

    passed = sum(report["passed"] for report in case_reports)
    latencies = [report["latency_ms"] for report in case_reports]
    report = {
        "cases": len(cases),
        "passed": passed,
        "pass_rate_pct": pct(passed, len(cases)),
        "embedding_model": args.embedding_model,
        "embedding_requests": retriever.embedding_requests,
        "embedding_input_tokens": retriever.embedding_input_tokens,
        "latency_ms": {
            "mean": round(mean(latencies), 3),
            "p50": round(median(latencies), 3),
            "p95": percentile(latencies, 0.95),
        },
        "failures": [
            case_report
            for case_report in case_reports
            if not case_report["passed"]
        ],
        "case_reports": case_reports,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({
        key: value for key, value in report.items() if key != "case_reports"
    }, indent=2))

    if report["pass_rate_pct"] < args.min_pass_rate:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
