#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--results",
        type=Path,
        default=Path("evals/commit05/reports/results_v1_gpt_5_6_luna_none.jsonl"),
    )
    p.add_argument("--report", type=Path, default=None)
    return p.parse_args()


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def pct(n: int, d: int) -> float:
    return round(100 * n / d, 2) if d else 0.0


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = max(0, math.ceil(p * len(ordered)) - 1)
    return round(ordered[idx], 4)


def mean(values: list[float | int]) -> float | None:
    return round(statistics.mean(values), 4) if values else None


def build_report(rows: list[dict]) -> dict:
    successes = [r for r in rows if r.get("api_success")]

    latencies = [r["metrics"]["latency_seconds"] for r in successes]
    input_tokens = [r["metrics"]["input_tokens"] for r in successes]
    output_tokens = [r["metrics"]["output_tokens"] for r in successes]
    reasoning_tokens = [r["metrics"].get("reasoning_tokens", 0) for r in successes]
    costs = [
        r["metrics"]["estimated_cost_usd"]
        for r in successes
        if r["metrics"].get("estimated_cost_usd") is not None
    ]

    by_type = defaultdict(lambda: {
        "cases": 0,
        "risk_correct": 0,
        "required_evidence_present": 0,
        "schema_valid": 0,
    })

    failures = []
    evidence_misses = []

    for r in rows:
        case = r["case"]
        case_type = case["case_type"]
        by_type[case_type]["cases"] += 1
        by_type[case_type]["schema_valid"] += int(bool(r.get("schema_valid")))
        by_type[case_type]["risk_correct"] += int(bool(r.get("risk_correct")))
        by_type[case_type]["required_evidence_present"] += int(
            bool(r.get("required_evidence_present"))
        )

        if r.get("api_success") and not r.get("risk_correct"):
            failures.append({
                "case_id": case["case_id"],
                "case_type": case_type,
                "expected": case["expected_risk_level"],
                "actual": r.get("assessment", {}).get("risk_level"),
            })

        if r.get("api_success") and not r.get("required_evidence_present"):
            evidence_misses.append({
                "case_id": case["case_id"],
                "case_type": case_type,
                "missing_required_evidence": r.get(
                    "missing_required_evidence",
                    [],
                ),
            })

    by_type_report = {}
    for case_type, vals in by_type.items():
        cases = vals["cases"]
        by_type_report[case_type] = {
            **vals,
            "risk_accuracy_pct": pct(vals["risk_correct"], cases),
            "required_evidence_rate_pct": pct(
                vals["required_evidence_present"],
                cases,
            ),
            "schema_valid_rate_pct": pct(vals["schema_valid"], cases),
        }

    prompt_versions = sorted({
        r.get("prompt_version")
        for r in rows
        if r.get("prompt_version")
    })
    model_values = sorted({
        r.get("metrics", {}).get("model")
        for r in successes
        if r.get("metrics", {}).get("model")
    })
    reasoning_values = sorted({
        str(r.get("run_config", {}).get("reasoning_effort"))
        for r in successes
        if r.get("run_config", {}).get("reasoning_effort")
    })

    return {
        "cases": len(rows),
        "successful_api_calls": len(successes),
        "prompt_versions": prompt_versions,
        "models": model_values,
        "reasoning_efforts": reasoning_values,
        "api_success_rate_pct": pct(len(successes), len(rows)),
        "schema_valid_rate_pct": pct(
            sum(bool(r.get("schema_valid")) for r in rows),
            len(rows),
        ),
        "risk_accuracy_pct": pct(
            sum(bool(r.get("risk_correct")) for r in successes),
            len(successes),
        ),
        "required_evidence_rate_pct": pct(
            sum(bool(r.get("required_evidence_present")) for r in successes),
            len(successes),
        ),
        "evidence_feature_validity_pct": pct(
            sum(bool(r.get("evidence_features_valid")) for r in successes),
            len(successes),
        ),
        "latency_seconds": {
            "mean": mean(latencies),
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
        },
        "tokens_per_request": {
            "mean_input": mean(input_tokens),
            "mean_output": mean(output_tokens),
            "mean_reasoning": mean(reasoning_tokens),
            "max_reasoning": max(reasoning_tokens) if reasoning_tokens else None,
            "total_reasoning": sum(reasoning_tokens),
        },
        "estimated_cost_usd": {
            "total": round(sum(costs), 6) if costs else None,
            "mean_per_request": round(statistics.mean(costs), 8)
            if costs else None,
        },
        "risk_accuracy_by_case_type": by_type_report,
        "risk_failures": failures,
        "evidence_misses": evidence_misses,
    }


def main():
    args = parse_args()
    rows = list(read_jsonl(args.results))
    report = build_report(rows)

    report_path = args.report
    if report_path is None:
        report_path = args.results.with_name(
            args.results.stem.replace("results_", "report_") + ".json"
        )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
