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
        default=Path("evals/commit04/results.jsonl"),
    )
    p.add_argument(
        "--report",
        type=Path,
        default=Path("evals/commit04/report.json"),
    )
    return p.parse_args()


def read_jsonl(path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def pct(n, d):
    return round(100 * n / d, 2) if d else 0.0


def percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    idx = max(0, math.ceil(p * len(values)) - 1)
    return round(values[idx], 4)


def main():
    args = parse_args()
    rows = list(read_jsonl(args.results))
    successes = [r for r in rows if r.get("api_success")]

    latencies = [r["metrics"]["latency_seconds"] for r in successes]
    input_tokens = [r["metrics"]["input_tokens"] for r in successes]
    output_tokens = [r["metrics"]["output_tokens"] for r in successes]
    costs = [
        r["metrics"]["estimated_cost_usd"]
        for r in successes
        if r["metrics"].get("estimated_cost_usd") is not None
    ]

    by_type = defaultdict(lambda: {"cases": 0, "risk_correct": 0})
    for r in successes:
        t = r["case"]["case_type"]
        by_type[t]["cases"] += 1
        by_type[t]["risk_correct"] += int(r.get("risk_correct", False))

    by_type_report = {}
    for t, vals in by_type.items():
        by_type_report[t] = {
            **vals,
            "risk_accuracy_pct": pct(vals["risk_correct"], vals["cases"]),
        }

    report = {
        "cases": len(rows),
        "successful_api_calls": len(successes),
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
            "mean": round(statistics.mean(latencies), 4) if latencies else None,
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
        },
        "tokens_per_request": {
            "mean_input": round(statistics.mean(input_tokens), 2)
                if input_tokens else None,
            "mean_output": round(statistics.mean(output_tokens), 2)
                if output_tokens else None,
        },
        "estimated_cost_usd": {
            "total": round(sum(costs), 6) if costs else None,
            "mean_per_request": round(statistics.mean(costs), 8)
                if costs else None,
        },
        "risk_accuracy_by_case_type": by_type_report,
    }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
