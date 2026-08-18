#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from evals.commit10.metrics import evaluate_case, mean, pct
from src.agent.investigator import AgentConfig
from src.tools import CDPTools, ToolRegistry
from src.workflow import LangGraphCustomerInvestigator
from src.workflow.investigator import WORKFLOW_VERSION

from .make_scenarios import read_jsonl, validate_scenarios


class InjectedCheckpointFailure(RuntimeError):
    pass


class ReplayResponses:
    def __init__(self, baseline_run: dict[str, Any], *, fail_first: bool) -> None:
        self.fail_first = fail_first
        self.calls = 0
        function_calls = [{
            "type": "function_call",
            "name": trace["tool_name"],
            "arguments": json.dumps(trace["arguments"], sort_keys=True),
            "call_id": f"replay-{index}",
        } for index, trace in enumerate(baseline_run["tool_trace"], start=1)]
        self.responses = [
            self._response("replay-tools", function_calls),
            self._response(
                "replay-answer",
                [],
                output_text=json.dumps(baseline_run["answer"], sort_keys=True),
            ),
        ]

    def create(self, **_: Any) -> Any:
        self.calls += 1
        if self.fail_first and self.calls == 1:
            raise InjectedCheckpointFailure("Injected failure before model completion")
        return self.responses.pop(0)

    @staticmethod
    def _response(
        response_id: str,
        output: list[dict[str, Any]],
        *,
        output_text: str = "",
    ) -> Any:
        return SimpleNamespace(
            id=response_id,
            model="gpt-5.6-luna",
            status="completed",
            output=output,
            output_text=output_text,
            usage=SimpleNamespace(
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                input_tokens_details=SimpleNamespace(cached_tokens=0),
                output_tokens_details=SimpleNamespace(reasoning_tokens=0),
            ),
        )


def run_benchmark(
    scenarios: list[dict[str, Any]],
    baseline_rows: list[dict[str, Any]],
    *,
    database: str,
    corpus_dir: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    validate_scenarios(scenarios)
    baseline_by_id = {
        row["case"]["case_id"]: row
        for row in baseline_rows
    }
    records = []
    with CDPTools(database, corpus_dir=corpus_dir) as tools:
        registry = ToolRegistry(tools)
        for scenario in scenarios:
            baseline = baseline_by_id[scenario["source_case_id"]]
            recover = scenario["mode"] == "checkpoint_recovery"
            responses = ReplayResponses(baseline["run"], fail_first=recover)
            workflow = LangGraphCustomerInvestigator(
                registry,
                config=AgentConfig(model="gpt-5.6-luna", reasoning_effort="none"),
                responses_client=responses,
            )
            thread_id = scenario["scenario_id"]
            injected_failure_observed = False
            record: dict[str, Any] = {"scenario": scenario}
            try:
                if recover:
                    try:
                        workflow.start(
                            baseline["case"]["customer_id"],
                            baseline["case"]["question"],
                            thread_id=thread_id,
                        )
                    except InjectedCheckpointFailure:
                        injected_failure_observed = True
                    run = workflow.resume(thread_id)
                else:
                    run = workflow.start(
                        baseline["case"]["customer_id"],
                        baseline["case"]["question"],
                        thread_id=thread_id,
                    )
                run_payload = run.model_dump(mode="json")
                evaluation = evaluate_case(baseline["case"], run_payload)
                actual_routes = run.workflow.routed_tool_nodes
                record.update({
                    "completed": True,
                    "correct_routing": actual_routes == scenario["expected_routes"],
                    "tool_calls_correct": (
                        run.metrics.tool_calls == scenario["expected_tool_calls"]
                    ),
                    "recovered": (
                        recover
                        and injected_failure_observed
                        and run.workflow.resume_count == 1
                    ),
                    "task_completed": evaluation["task_completed"],
                    "run": run_payload,
                })
            except Exception as exc:
                record.update({
                    "completed": False,
                    "correct_routing": False,
                    "tool_calls_correct": False,
                    "recovered": False,
                    "task_completed": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                })
            records.append(record)

    recovery_rows = [
        row for row in records
        if row["scenario"]["mode"] == "checkpoint_recovery"
    ]
    completed = [row for row in records if row["completed"]]
    tool_calls = [row["run"]["metrics"]["tool_calls"] for row in completed]
    checkpoints = [row["run"]["workflow"]["checkpoint_count"] for row in completed]
    report = {
        "scenarios": len(records),
        "completion_rate_pct": pct(sum(row["completed"] for row in records), len(records)),
        "correct_routing_rate_pct": pct(
            sum(row["correct_routing"] for row in records), len(records)
        ),
        "tool_calls_correct_rate_pct": pct(
            sum(row["tool_calls_correct"] for row in records), len(records)
        ),
        "task_completed_rate_pct": pct(
            sum(row["task_completed"] for row in records), len(records)
        ),
        "average_tool_calls": mean(tool_calls),
        "failed_executions": sum(not row["completed"] for row in records),
        "recovery_rate_pct": pct(
            sum(row["recovered"] for row in recovery_rows), len(recovery_rows)
        ),
        "checkpoint_count": {
            "mean": mean(checkpoints),
            "min": min(checkpoints) if checkpoints else None,
            "max": max(checkpoints) if checkpoints else None,
        },
        "safety": {
            "analysis_only_rate_pct": pct(
                sum(
                    row["run"]["workflow"]["recommendation"] == "ANALYSIS_ONLY"
                    for row in completed
                ),
                len(records),
            ),
            "approval_required_count": sum(
                row["run"]["workflow"]["approval_required"] for row in completed
            ),
            "actions_executed_count": sum(
                row["run"]["workflow"]["action_executed"] for row in completed
            ),
        },
        "workflow_version": WORKFLOW_VERSION,
        "model": "gpt-5.6-luna",
        "reasoning_effort": "none",
        "experiment_design": (
            "Deterministic replay of 50 accepted Commit 10 runs in standard and "
            "checkpoint-recovery modes. This measures orchestration, not new model quality."
        ),
        "failures": [{
            "scenario_id": row["scenario"]["scenario_id"],
            "error_type": row.get("error_type"),
            "error": row.get("error"),
            "correct_routing": row["correct_routing"],
            "tool_calls_correct": row["tool_calls_correct"],
            "recovered": row["recovered"],
            "task_completed": row["task_completed"],
        } for row in records if not all((
            row["completed"],
            row["correct_routing"],
            row["tool_calls_correct"],
            row["task_completed"],
            row["recovered"] if row["scenario"]["mode"] == "checkpoint_recovery" else True,
        ))],
    }
    return records, report


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="data/warehouse/signaldesk.duckdb")
    parser.add_argument("--corpus-dir", default="data/generated/knowledge")
    parser.add_argument(
        "--scenarios",
        type=Path,
        default=Path("evals/commit11/scenarios.jsonl"),
    )
    parser.add_argument(
        "--baseline-results",
        type=Path,
        default=Path("evals/commit10/reports/v4_full_results.jsonl"),
    )
    parser.add_argument(
        "--results",
        type=Path,
        default=Path("evals/commit11/reports/replay_results.jsonl"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("evals/commit11/reports/replay_report.json"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    scenarios = read_jsonl(args.scenarios)
    records, report = run_benchmark(
        scenarios,
        read_jsonl(args.baseline_results),
        database=args.database,
        corpus_dir=args.corpus_dir,
    )
    report["run_config"] = {
        "scenarios_file": str(args.scenarios),
        "scenarios_sha256": hashlib.sha256(args.scenarios.read_bytes()).hexdigest(),
        "baseline_results_file": str(args.baseline_results),
        "baseline_results_sha256": hashlib.sha256(
            args.baseline_results.read_bytes()
        ).hexdigest(),
    }
    write_jsonl(args.results, records)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
