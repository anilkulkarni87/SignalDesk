#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from evals.commit05.metrics import build_report, read_jsonl


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument(
        "--report",
        type=Path,
        default=Path("evals/commit05/reports/compare_v1_vs_v2.json"),
    )
    return p.parse_args()


def by_case(rows: list[dict]) -> dict[str, dict]:
    return {row["case"]["case_id"]: row for row in rows}


def score(row: dict) -> int:
    return int(bool(row.get("risk_correct"))) + int(
        bool(row.get("required_evidence_present"))
    )


def delta(candidate_value, baseline_value):
    if candidate_value is None or baseline_value is None:
        return None
    return round(candidate_value - baseline_value, 6)


def metric_deltas(candidate_report: dict, baseline_report: dict) -> dict:
    return {
        "risk_accuracy_pct": delta(
            candidate_report["risk_accuracy_pct"],
            baseline_report["risk_accuracy_pct"],
        ),
        "required_evidence_rate_pct": delta(
            candidate_report["required_evidence_rate_pct"],
            baseline_report["required_evidence_rate_pct"],
        ),
        "schema_valid_rate_pct": delta(
            candidate_report["schema_valid_rate_pct"],
            baseline_report["schema_valid_rate_pct"],
        ),
        "mean_latency_seconds": delta(
            candidate_report["latency_seconds"]["mean"],
            baseline_report["latency_seconds"]["mean"],
        ),
        "p95_latency_seconds": delta(
            candidate_report["latency_seconds"]["p95"],
            baseline_report["latency_seconds"]["p95"],
        ),
        "mean_input_tokens": delta(
            candidate_report["tokens_per_request"]["mean_input"],
            baseline_report["tokens_per_request"]["mean_input"],
        ),
        "mean_output_tokens": delta(
            candidate_report["tokens_per_request"]["mean_output"],
            baseline_report["tokens_per_request"]["mean_output"],
        ),
        "mean_cost_usd": delta(
            candidate_report["estimated_cost_usd"]["mean_per_request"],
            baseline_report["estimated_cost_usd"]["mean_per_request"],
        ),
    }


def summarize_case(case_id: str, baseline: dict, candidate: dict) -> dict:
    return {
        "case_id": case_id,
        "case_type": baseline["case"]["case_type"],
        "expected_risk_level": baseline["case"]["expected_risk_level"],
        "baseline_risk": baseline.get("assessment", {}).get("risk_level"),
        "candidate_risk": candidate.get("assessment", {}).get("risk_level"),
        "baseline_risk_correct": bool(baseline.get("risk_correct")),
        "candidate_risk_correct": bool(candidate.get("risk_correct")),
        "baseline_required_evidence": bool(
            baseline.get("required_evidence_present")
        ),
        "candidate_required_evidence": bool(
            candidate.get("required_evidence_present")
        ),
        "candidate_missing_required_evidence": candidate.get(
            "missing_required_evidence",
            [],
        ),
    }


def main():
    args = parse_args()
    baseline_rows = list(read_jsonl(args.baseline))
    candidate_rows = list(read_jsonl(args.candidate))

    baseline_report = build_report(baseline_rows)
    candidate_report = build_report(candidate_rows)

    baseline_cases = by_case(baseline_rows)
    candidate_cases = by_case(candidate_rows)
    common_case_ids = sorted(set(baseline_cases) & set(candidate_cases))

    regressions = []
    improvements = []
    changed = []

    for case_id in common_case_ids:
        baseline = baseline_cases[case_id]
        candidate = candidate_cases[case_id]
        baseline_score = score(baseline)
        candidate_score = score(candidate)

        summary = summarize_case(case_id, baseline, candidate)
        if candidate_score < baseline_score:
            regressions.append(summary)
        elif candidate_score > baseline_score:
            improvements.append(summary)

        if (
            baseline.get("assessment", {}).get("risk_level")
            != candidate.get("assessment", {}).get("risk_level")
        ):
            changed.append(summary)

    baseline_costs = [
        r["metrics"]["estimated_cost_usd"]
        for r in baseline_rows
        if r.get("api_success")
        and r.get("metrics", {}).get("estimated_cost_usd") is not None
    ]
    candidate_costs = [
        r["metrics"]["estimated_cost_usd"]
        for r in candidate_rows
        if r.get("api_success")
        and r.get("metrics", {}).get("estimated_cost_usd") is not None
    ]

    report = {
        "baseline_file": str(args.baseline),
        "candidate_file": str(args.candidate),
        "common_cases": len(common_case_ids),
        "baseline_summary": baseline_report,
        "candidate_summary": candidate_report,
        "metric_deltas": metric_deltas(candidate_report, baseline_report),
        "regression_count": len(regressions),
        "improvement_count": len(improvements),
        "changed_risk_count": len(changed),
        "regressions": regressions,
        "improvements": improvements,
        "changed_risk_cases": changed,
        "decision_inputs": {
            "candidate_has_regressions": bool(regressions),
            "candidate_mean_cost_usd": (
                round(statistics.mean(candidate_costs), 8)
                if candidate_costs else None
            ),
            "baseline_mean_cost_usd": (
                round(statistics.mean(baseline_costs), 8)
                if baseline_costs else None
            ),
        },
    }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
