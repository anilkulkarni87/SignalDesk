#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from src.workflow.investigator import TOOL_ROUTES


SCENARIO_VERSION = "commit11_v1_two_modes_per_frozen_case"
SCENARIO_MODES = ("standard", "checkpoint_recovery")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def build_scenarios(baseline_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(baseline_rows) != 50:
        raise ValueError(f"Expected 50 Commit 10 baseline rows, found {len(baseline_rows)}")
    scenarios = []
    for row in baseline_rows:
        if not row.get("api_success") or not row.get("evaluation", {}).get("task_completed"):
            raise ValueError(
                f"Baseline case is not accepted: {row.get('case', {}).get('case_id')}"
            )
        expected_routes = [
            TOOL_ROUTES[trace["tool_name"]]
            for trace in row["run"]["tool_trace"]
        ]
        for mode in SCENARIO_MODES:
            scenarios.append({
                "scenario_id": f"{row['case']['case_id']}__{mode}",
                "scenario_version": SCENARIO_VERSION,
                "source_case_id": row["case"]["case_id"],
                "mode": mode,
                "expected_routes": expected_routes,
                "expected_tool_calls": len(row["run"]["tool_trace"]),
            })
    return scenarios


def validate_scenarios(scenarios: list[dict[str, Any]]) -> None:
    if len(scenarios) != 100:
        raise ValueError(f"Expected 100 workflow scenarios, found {len(scenarios)}")
    if len({item["scenario_id"] for item in scenarios}) != 100:
        raise ValueError("Workflow scenario IDs must be unique")
    source_counts = {
        case_id: sum(item["source_case_id"] == case_id for item in scenarios)
        for case_id in {item["source_case_id"] for item in scenarios}
    }
    if len(source_counts) != 50 or set(source_counts.values()) != {2}:
        raise ValueError("Each of 50 source cases must have exactly two scenarios")
    if {item["mode"] for item in scenarios} != set(SCENARIO_MODES):
        raise ValueError("Scenario modes do not match the frozen experiment")
    if {item["scenario_version"] for item in scenarios} != {SCENARIO_VERSION}:
        raise ValueError("Scenario version does not match the generator")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--baseline-results",
        type=Path,
        default=Path("evals/commit10/reports/v4_full_results.jsonl"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/commit11/scenarios.jsonl"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    scenarios = build_scenarios(read_jsonl(args.baseline_results))
    validate_scenarios(scenarios)
    write_jsonl(args.output, scenarios)
    print(json.dumps({
        "scenarios": len(scenarios),
        "scenario_version": SCENARIO_VERSION,
        "baseline_sha256": hashlib.sha256(args.baseline_results.read_bytes()).hexdigest(),
        "output": str(args.output),
    }, indent=2))


if __name__ == "__main__":
    main()
