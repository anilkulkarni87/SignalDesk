#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from evals.commit08.matrix import (
    build_treatment_metadata,
    read_json,
    selection_analysis,
    validate_contract,
)
from evals.commit08.metrics import file_sha256, validate_frozen_inputs
from src.retrieval.documents import load_documents


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path("evals/commit08/experiment_contract.json"),
    )
    parser.add_argument(
        "--matrix",
        type=Path,
        default=Path("evals/commit08/reports/retrieval_experiment_matrix.json"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("evals/commit08/reports/retrieval_experiment_analysis.json"),
    )
    return parser.parse_args()


def case_report(summary: dict[str, Any], case_id: str) -> dict[str, Any]:
    return next(
        report for report in summary["case_reports"] if report["case_id"] == case_id
    )


def classify_experiments(
    summaries: dict[str, dict[str, Any]],
    comparisons: dict[str, dict[str, Any]],
    baseline_id: str,
) -> dict[str, dict[str, Any]]:
    baseline = summaries[baseline_id]
    classifications = {}
    for experiment_id, summary in summaries.items():
        comparison = comparisons.get(experiment_id, {})
        if experiment_id == baseline_id:
            decision = "retain_baseline"
            reason = "Incumbent treatment; no tested alternative produced a strict improvement."
        elif summary["equivalent_to_baseline"]:
            decision = "not_a_distinct_treatment"
            reason = (
                "Chunk content, retrieval strategy, filters, and ranking parameters "
                "are identical to the baseline; latency differences are run noise."
            )
        elif summary["current_approved_result_rate_at_5_pct"] < 100.0:
            decision = "reject_governance_failure"
            reason = "Top-five results are not entirely current and approved."
        elif comparison.get("regressed_cases_at_5"):
            decision = "reject_retrieval_regressions"
            reason = (
                f"Introduced {len(comparison['regressed_cases_at_5'])} "
                "complete-selector regression(s) at rank five."
            )
        elif all([
            summary["all_selector_coverage_at_5_pct"]
            >= baseline["all_selector_coverage_at_5_pct"],
            summary["mrr"] > baseline["mrr"],
        ]):
            decision = "generation_gate_candidate"
            reason = "Strict retrieval improvement with no rank-five selector regression."
        else:
            decision = "reject_no_improvement"
            reason = "Did not improve the frozen retrieval baseline."
        classifications[experiment_id] = {
            "decision": decision,
            "reason": reason,
            "hit_rate_at_5_pct": summary["hit_rate_at_5_pct"],
            "all_selector_coverage_at_5_pct": summary[
                "all_selector_coverage_at_5_pct"
            ],
            "mrr": summary["mrr"],
            "p95_latency_ms": summary["latency_ms"]["p95"],
            "current_approved_result_rate_at_5_pct": summary[
                "current_approved_result_rate_at_5_pct"
            ],
            "equivalent_to_baseline": summary["equivalent_to_baseline"],
            "regressed_cases_at_5": comparison.get("regressed_cases_at_5", []),
            "improved_cases_at_5": comparison.get("improved_cases_at_5", []),
        }
    return classifications


def build_analysis(
    contract: dict[str, Any],
    matrix: dict[str, Any],
    matrix_path: Path,
) -> dict[str, Any]:
    experiments = contract["experiments"]
    documents = load_documents(contract["corpus_dir"])
    treatment_metadata = build_treatment_metadata(contract, experiments, documents)
    summaries = matrix["experiments"]
    comparisons = matrix["comparisons_to_baseline"]
    baseline_id = contract["baseline_experiment_id"]
    corrected_selection = selection_analysis(
        summaries,
        comparisons,
        baseline_id=baseline_id,
        treatment_metadata=treatment_metadata,
    )
    classifications = classify_experiments(summaries, comparisons, baseline_id)

    build_by_table = {
        build["index_table"]: build for build in matrix.get("index_builds", [])
    }
    total_index_tokens = sum(
        build.get("embedding_input_tokens", 0) for build in build_by_table.values()
    )
    total_build_latency_ms = sum(
        build.get("total_build_latency_ms", 0.0) for build in build_by_table.values()
    )
    duplicate_overlap_tokens = build_by_table.get(
        "commit08_chunks_220_0", {}
    ).get("embedding_input_tokens", 0)

    retention = {
        experiment_id: {
            "first_relevant_rank": case_report(summary, "retention_02")[
                "first_relevant_rank"
            ],
            "all_selectors_at_5": case_report(summary, "retention_02")[
                "all_selectors_at_5"
            ],
        }
        for experiment_id, summary in summaries.items()
    }
    cross_family = {
        experiment_id: {
            "selector_recall_at_5": case_report(summary, "cross_family_01")[
                "selector_recall_at_5"
            ],
            "selector_recall_at_10": case_report(summary, "cross_family_01")[
                "selector_recall_at_10"
            ],
        }
        for experiment_id, summary in summaries.items()
    }

    return {
        "experiment_version": contract["experiment_version"],
        "source_matrix": str(matrix_path),
        "source_matrix_sha256": file_sha256(matrix_path),
        "corrected_selection": corrected_selection,
        "decision": {
            "adopted_retriever": baseline_id,
            "new_generation_gate_required": False,
            "reason": (
                "No distinct retrieval treatment strictly improved the baseline "
                "without governance failures or rank-five selector regressions. "
                "The Commit 07 baseline remains adopted, so rerunning 100 LLM calls "
                "would not test a new retrieval hypothesis."
            ),
        },
        "experiment_classifications": classifications,
        "index_build_analysis": {
            "total_embedding_input_tokens": total_index_tokens,
            "query_embedding_input_tokens": matrix["query_embedding"]["input_tokens"],
            "total_build_latency_ms": round(total_build_latency_ms, 3),
            "duplicate_no_overlap_embedding_tokens": duplicate_overlap_tokens,
            "lesson": (
                "The 220/0 and 220/40 chunk outputs are byte-identical. A treatment "
                "fingerprint should be checked before paying to embed both variants."
            ),
        },
        "persistent_failure_analysis": {
            "retention_02": {
                "classification": "ranking_ambiguity",
                "result_by_experiment": retention,
                "finding": (
                    "The vector baseline retrieves the right retention topic at rank "
                    "eight. Lexical and hybrid move it into the top five, but their "
                    "global configurations introduce broader regressions."
                ),
            },
            "cross_family_01": {
                "classification": "query_decomposition_failure",
                "result_by_experiment": cross_family,
                "finding": (
                    "Every strategy covers only one of two required policy selectors, "
                    "including at rank ten. Increasing K or globally fusing rankings "
                    "does not solve the missing intent."
                ),
            },
        },
        "next_hypothesis": {
            "statement": (
                "Explicitly decomposing multi-intent policy questions before retrieval "
                "should recover each required family without weakening strong single-"
                "intent vector rankings."
            ),
            "boundary": (
                "Test on a newly frozen multi-intent retrieval set before changing the "
                "adopted Commit 07 pipeline; do not tune against the single existing "
                "cross-family case."
            ),
        },
    }


def main() -> None:
    args = parse_args()
    contract = read_json(args.contract)
    validate_contract(contract)
    validate_frozen_inputs(contract)
    matrix = read_json(args.matrix)
    analysis = build_analysis(contract, matrix, args.matrix)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(analysis, indent=2), encoding="utf-8")
    print(json.dumps(analysis, indent=2))


if __name__ == "__main__":
    main()
