#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any

from src.tools import CDPTools, ToolRegistry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="data/warehouse/signaldesk.duckdb")
    parser.add_argument("--corpus-dir", default="data/generated/knowledge")
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("evals/commit09/cases.jsonl"),
    )
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument(
        "--coverage-json",
        type=Path,
        default=Path("evals/commit09/reports/coverage.json"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("evals/commit09/reports/tool_benchmark.json"),
    )
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def pct(numerator: int, denominator: int) -> float:
    return round(100 * numerator / denominator, 2) if denominator else 0.0


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return round(ordered[index], 3)


def summarize_tool(tool_name: str, reports: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [report for report in reports if report["expected_success"]]
    invalid = [report for report in reports if not report["expected_success"]]
    valid_latencies = [
        latency
        for report in valid
        for latency in report["latencies_ms"]
    ]
    return {
        "tool_name": tool_name,
        "cases": len(reports),
        "valid_cases": len(valid),
        "invalid_cases": len(invalid),
        "valid_input_success_rate_pct": pct(
            sum(report["passed"] for report in valid), len(valid)
        ),
        "invalid_input_behavior_rate_pct": pct(
            sum(report["passed"] for report in invalid), len(invalid)
        ),
        "valid_latency_ms": {
            "mean": round(mean(valid_latencies), 3) if valid_latencies else 0.0,
            "p50": round(median(valid_latencies), 3) if valid_latencies else 0.0,
            "p95": percentile(valid_latencies, 0.95),
        },
        "failures": [report for report in reports if not report["passed"]],
    }


def main() -> None:
    args = parse_args()
    if args.repetitions <= 0:
        raise ValueError("repetitions must be positive")
    cases = read_jsonl(args.cases)
    if len(cases) != 105:
        raise ValueError(f"Expected 105 frozen tool cases, found {len(cases)}")

    with CDPTools(args.database, corpus_dir=args.corpus_dir) as tools:
        registry = ToolRegistry(tools)
        valid_tool_names = {definition["name"] for definition in registry.definitions()}
        if {case["tool_name"] for case in cases} != valid_tool_names:
            raise ValueError("Cases do not cover every registered tool exactly")

        for case in cases:
            registry.execute(case["tool_name"], case["arguments"])

        case_reports = []
        for case in cases:
            results = [
                registry.execute(case["tool_name"], case["arguments"])
                for _ in range(args.repetitions)
            ]
            observed_codes = [
                result.error.code if result.error else None for result in results
            ]
            if case["expected_success"]:
                passed = all(result.success and result.output is not None for result in results)
            else:
                passed = all([
                    not result.success
                    and result.error is not None
                    and result.error.code == case["expected_error_code"]
                    for result in results
                ])
            case_reports.append({
                **case,
                "passed": passed,
                "observed_success": [result.success for result in results],
                "observed_error_codes": observed_codes,
                "latencies_ms": [result.latency_ms for result in results],
            })

        by_tool: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for report in case_reports:
            by_tool[report["tool_name"]].append(report)
        tool_summaries = {
            tool_name: summarize_tool(tool_name, reports)
            for tool_name, reports in sorted(by_tool.items())
        }

        coverage = None
        if args.coverage_json.exists():
            coverage_report = json.loads(args.coverage_json.read_text(encoding="utf-8"))
            coverage = {
                "line_coverage_pct": coverage_report["totals"]["percent_covered"],
                "covered_lines": coverage_report["totals"]["covered_lines"],
                "num_statements": coverage_report["totals"]["num_statements"],
                "covered_branches": coverage_report["totals"]["covered_branches"],
                "num_branches": coverage_report["totals"]["num_branches"],
                "target_pct": 80.0,
                "passed": coverage_report["totals"]["percent_covered"] > 80.0,
            }

        report = {
            "cases_file": str(args.cases),
            "cases": len(cases),
            "repetitions": args.repetitions,
            "executions": len(cases) * args.repetitions,
            "tool_contracts": registry.definitions(),
            "tools": tool_summaries,
            "overall": {
                "valid_input_success_rate_pct": pct(
                    sum(
                        report["passed"]
                        for report in case_reports
                        if report["expected_success"]
                    ),
                    sum(report["expected_success"] for report in case_reports),
                ),
                "invalid_input_behavior_rate_pct": pct(
                    sum(
                        report["passed"]
                        for report in case_reports
                        if not report["expected_success"]
                    ),
                    sum(not report["expected_success"] for report in case_reports),
                ),
                "failed_cases": sum(not report["passed"] for report in case_reports),
            },
            "coverage": coverage,
            "case_reports": case_reports,
        }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({
        **{key: value for key, value in report.items() if key not in {
            "tool_contracts", "case_reports", "tools"
        }},
        "tools": {
            name: {key: value for key, value in summary.items() if key != "failures"}
            for name, summary in tool_summaries.items()
        },
    }, indent=2))


if __name__ == "__main__":
    main()
