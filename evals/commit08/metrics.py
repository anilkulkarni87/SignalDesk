from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable

from src.retrieval.documents import KnowledgeDocument


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def corpus_sha256(corpus_dir: str | Path) -> str:
    root = Path(corpus_dir)
    digest = hashlib.sha256()
    paths = sorted(path for path in root.rglob("*") if path.is_file())
    for path in paths:
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def chunk_content_sha256(chunks: Iterable[Any]) -> str:
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk.chunk_id.encode("utf-8"))
        digest.update(b"\0")
        digest.update(chunk.embedding_text.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def treatment_sha256(
    experiment: dict[str, Any],
    *,
    chunk_sha256: str | None,
    candidate_pool: int,
    rank_constant: int,
) -> str:
    treatment = {
        "strategy": experiment["strategy"],
        "filter_current_approved": experiment["filter_current_approved"],
        "chunk_content_sha256": chunk_sha256,
        "candidate_pool": candidate_pool,
        "rank_constant": rank_constant
        if experiment["strategy"] == "hybrid_rrf"
        else None,
        "vector_weight": experiment.get("vector_weight")
        if experiment["strategy"] == "vector_lexical_rerank"
        else None,
    }
    payload = json.dumps(treatment, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_frozen_inputs(contract: dict[str, Any]) -> None:
    actual_cases = file_sha256(contract["cases_file"])
    if actual_cases != contract["cases_sha256"]:
        raise ValueError(
            "Frozen retrieval cases changed: "
            f"expected {contract['cases_sha256']}, found {actual_cases}"
        )

    actual_corpus = corpus_sha256(contract["corpus_dir"])
    if actual_corpus != contract["corpus_sha256"]:
        raise ValueError(
            "Frozen knowledge corpus changed: "
            f"expected {contract['corpus_sha256']}, found {actual_corpus}"
        )


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return round(ordered[index], 3)


def _selector_matches(
    document: KnowledgeDocument,
    selector: dict[str, str],
) -> bool:
    return (
        document.family == selector["family"]
        and str(document.metadata.get("topic", "")) == selector["topic"]
    )


def score_case(
    case: dict[str, Any],
    retrieved_ids: list[str],
    documents_by_id: dict[str, KnowledgeDocument],
    *,
    ranks: Iterable[int],
    latency_ms: float,
) -> dict[str, Any]:
    unique_ids = list(dict.fromkeys(retrieved_ids))
    relevant = set(case["relevant_document_ids"])
    selectors = case["relevance_selectors"]
    first_rank = next(
        (
            rank
            for rank, document_id in enumerate(unique_ids, start=1)
            if document_id in relevant
        ),
        None,
    )
    report: dict[str, Any] = {
        "case_id": case["case_id"],
        "category": case["category"],
        "query": case["query"],
        "relevant_document_ids": sorted(relevant),
        "relevance_selectors": selectors,
        "retrieved_document_ids": unique_ids,
        "first_relevant_rank": first_rank,
        "reciprocal_rank": round(1 / first_rank, 6) if first_rank else 0.0,
        "latency_ms": round(latency_ms, 3),
    }

    for rank in ranks:
        top_ids = unique_ids[:rank]
        top_documents = [documents_by_id[document_id] for document_id in top_ids]
        relevant_count = len(relevant & set(top_ids))
        matched_selectors = sum(
            any(_selector_matches(document, selector) for document in top_documents)
            for selector in selectors
        )
        report[f"hit_at_{rank}"] = relevant_count > 0
        report[f"document_recall_at_{rank}"] = round(
            relevant_count / len(relevant), 6
        )
        report[f"precision_at_{rank}"] = round(
            relevant_count / len(top_ids), 6
        ) if top_ids else 0.0
        report[f"selector_recall_at_{rank}"] = round(
            matched_selectors / len(selectors), 6
        )
        report[f"all_selectors_at_{rank}"] = matched_selectors == len(selectors)
        report[f"current_approved_rate_at_{rank}"] = round(
            sum(
                document.status == "CURRENT" and document.authority == "APPROVED"
                for document in top_documents
            ) / len(top_documents),
            6,
        ) if top_documents else 0.0
    return report


def summarize_experiment(
    experiment: dict[str, Any],
    case_reports: list[dict[str, Any]],
    *,
    ranks: Iterable[int],
    index_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ranks = list(ranks)
    count = len(case_reports)
    latencies = [report["latency_ms"] for report in case_reports]
    summary: dict[str, Any] = {
        "experiment_id": experiment["experiment_id"],
        "strategy": experiment["strategy"],
        "hypothesis": experiment["hypothesis"],
        "filter_current_approved": experiment["filter_current_approved"],
        "cases": count,
        "metric_definitions": {
            "hit_rate_at_k": (
                "Percentage of queries with at least one curated relevant "
                "document in the top K document-level results."
            ),
            "all_selector_coverage_at_k": (
                "Percentage of queries whose top K results cover every curated "
                "family/topic selector; unlike hit rate, this detects a missing "
                "side of a cross-family query."
            ),
            "document_recall_at_k": (
                "Mean fraction of all interchangeable curated relevant documents "
                "retrieved in the top K."
            ),
        },
        "mrr": round(mean(report["reciprocal_rank"] for report in case_reports), 4)
        if case_reports else 0.0,
        "latency_ms": {
            "mean": round(mean(latencies), 3) if latencies else 0.0,
            "p50": round(median(latencies), 3) if latencies else 0.0,
            "p95": percentile(latencies, 0.95),
        },
        "index_metadata": index_metadata,
    }

    for rank in ranks:
        summary[f"hit_rate_at_{rank}_pct"] = round(
            100 * sum(report[f"hit_at_{rank}"] for report in case_reports) / count,
            2,
        ) if count else 0.0
        summary[f"all_selector_coverage_at_{rank}_pct"] = round(
            100
            * sum(report[f"all_selectors_at_{rank}"] for report in case_reports)
            / count,
            2,
        ) if count else 0.0
        summary[f"mean_selector_recall_at_{rank}_pct"] = round(
            100
            * mean(report[f"selector_recall_at_{rank}"] for report in case_reports),
            2,
        ) if case_reports else 0.0
        summary[f"mean_document_recall_at_{rank}_pct"] = round(
            100
            * mean(report[f"document_recall_at_{rank}"] for report in case_reports),
            2,
        ) if case_reports else 0.0
        summary[f"mean_precision_at_{rank}_pct"] = round(
            100 * mean(report[f"precision_at_{rank}"] for report in case_reports),
            2,
        ) if case_reports else 0.0
        summary[f"current_approved_result_rate_at_{rank}_pct"] = round(
            100
            * mean(
                report[f"current_approved_rate_at_{rank}"]
                for report in case_reports
            ),
            2,
        ) if case_reports else 0.0

    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for report in case_reports:
        by_category[report["category"]].append(report)
    summary["by_category"] = {
        category: {
            "cases": len(reports),
            "hit_rate_at_5_pct": round(
                100 * sum(report["hit_at_5"] for report in reports) / len(reports),
                2,
            ),
            "all_selector_coverage_at_5_pct": round(
                100
                * sum(report["all_selectors_at_5"] for report in reports)
                / len(reports),
                2,
            ),
        }
        for category, reports in sorted(by_category.items())
    }
    summary["failures_at_5"] = [
        report["case_id"]
        for report in case_reports
        if not report["all_selectors_at_5"]
    ]
    summary["case_reports"] = case_reports
    return summary


def compare_to_baseline(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    baseline_cases = {
        report["case_id"]: report for report in baseline["case_reports"]
    }
    candidate_cases = {
        report["case_id"]: report for report in candidate["case_reports"]
    }
    shared = sorted(set(baseline_cases) & set(candidate_cases))
    return {
        "baseline_experiment_id": baseline["experiment_id"],
        "candidate_experiment_id": candidate["experiment_id"],
        "shared_cases": len(shared),
        "delta_hit_rate_at_5_pct": round(
            candidate["hit_rate_at_5_pct"] - baseline["hit_rate_at_5_pct"], 2
        ),
        "delta_all_selector_coverage_at_5_pct": round(
            candidate["all_selector_coverage_at_5_pct"]
            - baseline["all_selector_coverage_at_5_pct"],
            2,
        ),
        "delta_mrr": round(candidate["mrr"] - baseline["mrr"], 4),
        "delta_p95_latency_ms": round(
            candidate["latency_ms"]["p95"] - baseline["latency_ms"]["p95"],
            3,
        ),
        "improved_cases_at_5": [
            case_id
            for case_id in shared
            if not baseline_cases[case_id]["all_selectors_at_5"]
            and candidate_cases[case_id]["all_selectors_at_5"]
        ],
        "regressed_cases_at_5": [
            case_id
            for case_id in shared
            if baseline_cases[case_id]["all_selectors_at_5"]
            and not candidate_cases[case_id]["all_selectors_at_5"]
        ],
    }
