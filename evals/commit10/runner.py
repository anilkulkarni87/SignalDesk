#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from src.agent import AgentConfig, CustomerInvestigator
from src.agent.prompts import PROMPT_VERSION
from src.tools import CDPTools, ToolRegistry

from .make_cases import RUBRIC_VERSION
from .metrics import EVALUATION_VERSION, build_report, evaluate_case


EXPECTED_TASK_COUNTS = {
    "behavior_investigation": 10,
    "campaign_readiness": 5,
    "multi_signal_investigation": 10,
    "profile_lookup": 5,
    "purchase_investigation": 10,
    "support_policy_investigation": 10,
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def validate_frozen_cases(cases: list[dict[str, Any]]) -> None:
    if len(cases) != 50:
        raise ValueError(f"Expected 50 frozen agent tasks, found {len(cases)}")
    if len({case["case_id"] for case in cases}) != 50:
        raise ValueError("Frozen agent case IDs must be unique")
    if len({case["customer_id"] for case in cases}) != 50:
        raise ValueError("Frozen agent tasks must use 50 unique customers")
    if {case["rubric_version"] for case in cases} != {RUBRIC_VERSION}:
        raise ValueError("Frozen agent rubric version does not match the runner")
    task_counts = {
        task_type: sum(case["task_type"] == task_type for case in cases)
        for task_type in EXPECTED_TASK_COUNTS
    }
    if task_counts != EXPECTED_TASK_COUNTS:
        raise ValueError(f"Unexpected task distribution: {task_counts}")
    for case in cases:
        expected = set(case["expected_tools"])
        if not expected or not expected.issubset(set(case["allowed_tools"])):
            raise ValueError(f"Invalid tool rubric in {case['case_id']}")
        if set(case["argument_rules"]) != expected:
            raise ValueError(f"Argument rules do not match tools in {case['case_id']}")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    temporary.replace(path)


def read_case_ids(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="data/warehouse/signaldesk.duckdb")
    parser.add_argument("--corpus-dir", default="data/generated/knowledge")
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("evals/commit10/cases.jsonl"),
    )
    parser.add_argument(
        "--results",
        type=Path,
        default=Path("evals/commit10/reports/v4_full_results.jsonl"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("evals/commit10/reports/v4_full_report.json"),
    )
    parser.add_argument("--model", default="gpt-5.6-luna")
    parser.add_argument("--reasoning-effort", choices=("none",), default="none")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--case-id-file", type=Path)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases = read_jsonl(args.cases)
    validate_frozen_cases(cases)
    requested_case_ids = list(args.case_id)
    if args.case_id_file:
        requested_case_ids.extend(read_case_ids(args.case_id_file))
    if requested_case_ids:
        requested = set(requested_case_ids)
        cases = [case for case in cases if case["case_id"] in requested]
        missing = requested - {case["case_id"] for case in cases}
        if missing:
            raise ValueError(f"Unknown case IDs: {sorted(missing)}")
    if args.limit is not None:
        if args.limit < 1:
            raise ValueError("limit must be positive")
        cases = cases[:args.limit]

    rows = read_jsonl(args.results) if args.resume and args.results.exists() else []
    completed_ids = {row["case"]["case_id"] for row in rows}
    with CDPTools(args.database, corpus_dir=args.corpus_dir) as tools:
        agent = CustomerInvestigator(
            ToolRegistry(tools),
            config=AgentConfig(
                model=args.model,
                reasoning_effort=args.reasoning_effort,
            ),
        )
        for case in cases:
            if case["case_id"] in completed_ids:
                continue
            record: dict[str, Any] = {"case": case}
            try:
                run = agent.investigate(case["customer_id"], case["question"])
                run_payload = run.model_dump(mode="json")
                record.update({
                    "api_success": True,
                    "run": run_payload,
                    "evaluation": evaluate_case(case, run_payload),
                })
            except Exception as exc:
                record.update({
                    "api_success": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "evaluation": {},
                })
            rows.append(record)
            write_jsonl(args.results, rows)
            print(json.dumps({
                "case_id": case["case_id"],
                "api_success": record["api_success"],
                "evaluation": record.get("evaluation", {}),
            }))

    selected_ids = {case["case_id"] for case in cases}
    selected_rows = [row for row in rows if row["case"]["case_id"] in selected_ids]
    report = build_report(selected_rows)
    report["run_config"] = {
        "cases_file": str(args.cases),
        "cases_sha256": hashlib.sha256(args.cases.read_bytes()).hexdigest(),
        "model": args.model,
        "prompt_version": PROMPT_VERSION,
        "evaluation_version": EVALUATION_VERSION,
        "reasoning_effort": args.reasoning_effort,
    }
    if args.case_id_file:
        report["run_config"]["case_id_file"] = str(args.case_id_file)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
