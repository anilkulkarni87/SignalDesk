#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean, median


BOOLEAN_METRICS = (
    "citation_resolution_valid",
    "risk_correct",
    "required_evidence_all_present",
    "required_evidence_any_present",
    "answer_correct",
    "expected_policy_docs_retrieved",
    "expected_policy_families_retrieved",
    "all_citations_retrieved",
    "all_citation_excerpts_grounded",
    "expected_policy_docs_cited",
    "expected_policy_families_cited",
    "unsupported_policy_claims_empty",
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--results",
        type=Path,
        default=Path("evals/commit07/reports/results.jsonl"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("evals/commit07/reports/report.json"),
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
    return round(ordered[index], 4)


def distribution(values: list[float]) -> dict:
    return {
        "mean": round(mean(values), 4) if values else 0.0,
        "p50": round(median(values), 4) if values else 0.0,
        "p95": percentile(values, 0.95),
    }


def metric_rates(rows: list[dict]) -> dict:
    return {
        f"{metric}_rate_pct": pct(
            sum(bool(row.get(metric)) for row in rows),
            len(rows),
        )
        for metric in BOOLEAN_METRICS
    }


def build_report(rows: list[dict]) -> dict:
    successes = [row for row in rows if row.get("api_success")]
    first_attempt_successes = [
        row
        for row in successes
        if row.get("first_attempt_api_success", False)
    ]
    by_question_type = defaultdict(list)
    for row in successes:
        by_question_type[row["case"]["question_type"]].append(row)

    retrieval_latencies = [
        row["metrics"]["retrieval_latency_seconds"] for row in successes
    ]
    generation_latencies = [
        row["metrics"]["generation_latency_seconds"] for row in successes
    ]
    total_latencies = [
        row["metrics"]["total_latency_seconds"] for row in successes
    ]
    citation_count = sum(row.get("citation_count", 0) for row in successes)
    grounded_citation_count = sum(
        row.get("citation_grounded_count", 0) for row in successes
    )
    total_cost = sum(
        row["metrics"].get("estimated_cost_usd") or 0.0
        for row in successes
    )

    failures = []
    for row in rows:
        failed_metrics = [
            metric for metric in BOOLEAN_METRICS if not row.get(metric, False)
        ]
        if not row.get("api_success") or failed_metrics:
            failures.append({
                "case_id": row["case"]["case_id"],
                "customer_id": row["case"]["customer_id"],
                "question_type": row["case"]["question_type"],
                "api_success": row.get("api_success", False),
                "error_type": row.get("error_type"),
                "error": row.get("error"),
                "failed_metrics": failed_metrics,
                "retrieved_policy_doc_ids": row.get(
                    "retrieved_policy_doc_ids",
                    [],
                ),
                "cited_policy_doc_ids": [
                    source["document_id"]
                    for source in row.get("assessment", {}).get(
                        "policy_sources",
                        [],
                    )
                ],
            })

    return {
        "cases": len(rows),
        "successful_api_calls": len(successes),
        "api_success_rate_pct": pct(len(successes), len(rows)),
        "first_attempt_successful_api_calls": len(first_attempt_successes),
        "first_attempt_api_success_rate_pct": pct(
            len(first_attempt_successes),
            len(rows),
        ),
        "api_retry_attempts_total": sum(
            max(0, int(row.get("api_attempts", 0)) - 1)
            for row in rows
        ),
        "schema_valid_rate_pct": pct(
            sum(bool(row.get("schema_valid")) for row in rows),
            len(rows),
        ),
        "schema_valid_given_api_success_rate_pct": pct(
            sum(bool(row.get("schema_valid")) for row in successes),
            len(successes),
        ),
        **metric_rates(successes),
        "citation_precision_pct": pct(
            grounded_citation_count,
            citation_count,
        ),
        "reasoning_tokens_total": sum(
            row["metrics"].get("reasoning_tokens", 0) for row in successes
        ),
        "latency_seconds": {
            "retrieval": distribution(retrieval_latencies),
            "generation": distribution(generation_latencies),
            "total": distribution(total_latencies),
        },
        "tokens": {
            "input_total": sum(
                row["metrics"].get("input_tokens", 0) for row in successes
            ),
            "cached_input_total": sum(
                row["metrics"].get("cached_input_tokens", 0)
                for row in successes
            ),
            "output_total": sum(
                row["metrics"].get("output_tokens", 0) for row in successes
            ),
            "total": sum(
                row["metrics"].get("total_tokens", 0) for row in successes
            ),
        },
        "estimated_generation_cost_usd": round(total_cost, 6),
        "by_question_type": {
            question_type: {
                "cases": len(question_rows),
                **metric_rates(question_rows),
            }
            for question_type, question_rows in sorted(by_question_type.items())
        },
        "failures": failures,
    }


def main():
    args = parse_args()
    rows = read_jsonl(args.results)
    report = build_report(rows)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
