#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from evals.commit10.metrics import build_report, evaluate_case
from evals.commit10.runner import (
    read_case_ids,
    read_jsonl,
    validate_frozen_cases,
    write_jsonl,
)
from src.agent import AgentConfig
from src.agent.prompts import PROMPT_VERSION
from src.tools import CDPTools, ToolRegistry
from src.workflow import LangGraphCustomerInvestigator
from src.workflow.investigator import WORKFLOW_VERSION


POLICY_RATE_NAMES = (
    "all_policy_citations_retrieved_rate_pct",
    "all_policy_citations_evidenced_rate_pct",
    "required_policy_families_cited_rate_pct",
)


def select_cases(
    cases: list[dict[str, Any]],
    *,
    case_ids: list[str],
    case_id_file: Path | None,
    limit: int | None,
) -> list[dict[str, Any]]:
    requested_case_ids = list(case_ids)
    if case_id_file is not None:
        requested_case_ids.extend(read_case_ids(case_id_file))
    if requested_case_ids:
        requested = set(requested_case_ids)
        selected = [case for case in cases if case["case_id"] in requested]
        missing = requested - {case["case_id"] for case in selected}
        if missing:
            raise ValueError(f"Unknown case IDs: {sorted(missing)}")
        cases = selected
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be positive")
        cases = cases[:limit]
    return cases


def mark_empty_policy_metrics_not_applicable(report: dict[str, Any]) -> None:
    if report["policy_tasks"]["cases"] != 0:
        return
    for name in POLICY_RATE_NAMES:
        report[name] = None
        report["policy_tasks"][name] = None
    report["policy_tasks"]["task_completed_rate_pct"] = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="data/warehouse/signaldesk.duckdb")
    parser.add_argument("--corpus-dir", default="data/generated/knowledge")
    parser.add_argument(
        "--cases", type=Path, default=Path("evals/commit10/cases.jsonl")
    )
    parser.add_argument(
        "--results",
        type=Path,
        default=Path("evals/commit11/reports/langgraph_results.jsonl"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("evals/commit11/reports/langgraph_report.json"),
    )
    parser.add_argument("--model", default="gpt-5.6-luna")
    parser.add_argument("--reasoning-effort", choices=("none",), default="none")
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--case-id-file", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases = read_jsonl(args.cases)
    validate_frozen_cases(cases)
    cases = select_cases(
        cases,
        case_ids=args.case_id,
        case_id_file=args.case_id_file,
        limit=args.limit,
    )

    rows = read_jsonl(args.results) if args.resume and args.results.exists() else []
    completed_ids = {row["case"]["case_id"] for row in rows}
    with CDPTools(args.database, corpus_dir=args.corpus_dir) as tools:
        workflow = LangGraphCustomerInvestigator(
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
                run = workflow.investigate(
                    case["customer_id"],
                    case["question"],
                    thread_id=f"commit11-{case['case_id']}",
                )
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
    mark_empty_policy_metrics_not_applicable(report)
    successful = [row for row in selected_rows if row.get("api_success")]
    report["workflow"] = {
        "workflow_version": WORKFLOW_VERSION,
        "completion_rate_pct": report["api_success_rate_pct"],
        "checkpoint_count_total": sum(
            row["run"]["workflow"]["checkpoint_count"] for row in successful
        ),
        "approval_required_count": sum(
            row["run"]["workflow"]["approval_required"] for row in successful
        ),
        "actions_executed_count": sum(
            row["run"]["workflow"]["action_executed"] for row in successful
        ),
    }
    report["run_config"] = {
        "cases_file": str(args.cases),
        "cases_sha256": hashlib.sha256(args.cases.read_bytes()).hexdigest(),
        "model": args.model,
        "prompt_version": PROMPT_VERSION,
        "workflow_version": WORKFLOW_VERSION,
        "reasoning_effort": args.reasoning_effort,
        "selected_case_ids": [case["case_id"] for case in cases],
    }
    if args.case_id_file is not None:
        report["run_config"]["case_id_file"] = str(args.case_id_file)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
