#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from evals.commit10.metrics import mean, pct
from evals.commit10.runner import read_jsonl
from src.workflow.investigator import TOOL_ROUTES


METRICS = (
    "correct_tools_selected",
    "correct_tool_arguments",
    "unnecessary_tools_empty",
    "conclusion_correct",
    "summary_complete",
    "all_evidence_grounded",
    "required_evidence_present",
    "all_policy_citations_retrieved",
    "all_policy_citations_evidenced",
    "required_policy_families_cited",
    "task_completed",
)


def metric_rates(rows: list[dict[str, Any]]) -> dict[str, float]:
    return {
        f"{name}_rate_pct": pct(
            sum(bool(row.get("evaluation", {}).get(name)) for row in rows),
            len(rows),
        )
        for name in METRICS
    }


def operational(rows: list[dict[str, Any]]) -> dict[str, Any]:
    successes = [row for row in rows if row.get("api_success")]
    return {
        "api_success_rate_pct": pct(len(successes), len(rows)),
        "mean_tool_calls": mean([
            row["run"]["metrics"]["tool_calls"] for row in successes
        ]),
        "mean_latency_seconds": mean([
            row["run"]["metrics"]["latency_seconds"] for row in successes
        ]),
        "input_tokens_total": sum(
            row["run"]["metrics"]["input_tokens"] for row in successes
        ),
        "output_tokens_total": sum(
            row["run"]["metrics"]["output_tokens"] for row in successes
        ),
        "estimated_cost_usd_total": round(sum(
            row["run"]["metrics"]["estimated_cost_usd"] or 0
            for row in successes
        ), 6),
    }


def compare(
    baseline_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if len(baseline_rows) != 50 or len(candidate_rows) != 50:
        raise ValueError("Comparison requires 50 baseline and 50 candidate rows")
    baseline = {row["case"]["case_id"]: row for row in baseline_rows}
    candidate = {row["case"]["case_id"]: row for row in candidate_rows}
    if baseline.keys() != candidate.keys():
        raise ValueError("Baseline and candidate case IDs do not match")

    baseline_rates = metric_rates(baseline_rows)
    candidate_rates = metric_rates(candidate_rows)
    rate_deltas = {
        name: round(candidate_rates[name] - baseline_rates[name], 2)
        for name in baseline_rates
    }
    regressions = []
    improvements = []
    per_case = []
    for case_id in sorted(baseline):
        before = baseline[case_id]
        after = candidate[case_id]
        before_complete = bool(before.get("evaluation", {}).get("task_completed"))
        after_complete = bool(after.get("evaluation", {}).get("task_completed"))
        if before_complete and not after_complete:
            regressions.append(case_id)
        if after_complete and not before_complete:
            improvements.append(case_id)
        per_case.append({
            "case_id": case_id,
            "baseline_task_completed": before_complete,
            "candidate_task_completed": after_complete,
            "candidate_failed_metrics": [
                name for name in METRICS
                if not after.get("evaluation", {}).get(name)
            ],
        })

    route_failures = []
    successful_candidates = [row for row in candidate_rows if row.get("api_success")]
    for row in successful_candidates:
        expected_routes = [
            TOOL_ROUTES[trace["tool_name"]]
            for trace in row["run"]["tool_trace"]
        ]
        actual_routes = row["run"]["workflow"]["routed_tool_nodes"]
        if actual_routes != expected_routes:
            route_failures.append(row["case"]["case_id"])

    return {
        "experiment": (
            "Same 50 frozen cases, prompt, tools, model, reasoning, schemas, and "
            "rubric; only manual-loop versus LangGraph orchestration changes."
        ),
        "baseline": {
            "name": "commit10_manual_loop_v4",
            "metrics": baseline_rates,
            "operational": operational(baseline_rows),
        },
        "candidate": {
            "name": "commit11_langgraph_workflow_v1",
            "metrics": candidate_rates,
            "operational": operational(candidate_rows),
        },
        "candidate_minus_baseline_rate_pct": rate_deltas,
        "behavioral_regressions": regressions,
        "behavioral_improvements": improvements,
        "correct_routing_rate_pct": pct(
            len(successful_candidates) - len(route_failures),
            len(candidate_rows),
        ),
        "routing_failures": route_failures,
        "safety": {
            "approval_required_count": sum(
                row["run"]["workflow"]["approval_required"]
                for row in successful_candidates
            ),
            "actions_executed_count": sum(
                row["run"]["workflow"]["action_executed"]
                for row in successful_candidates
            ),
        },
        "per_case": per_case,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("evals/commit10/reports/v4_full_results.jsonl"),
    )
    parser.add_argument(
        "--candidate",
        type=Path,
        default=Path("evals/commit11/reports/langgraph_results.jsonl"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/commit11/reports/compare_manual_vs_langgraph.json"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = compare(read_jsonl(args.baseline), read_jsonl(args.candidate))
    report["run_config"] = {
        "baseline_file": str(args.baseline),
        "baseline_sha256": hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
        "candidate_file": str(args.candidate),
        "candidate_sha256": hashlib.sha256(args.candidate.read_bytes()).hexdigest(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
