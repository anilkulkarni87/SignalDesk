#!/usr/bin/env python3

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any

import agents
import openai

from evals.commit12.make_cases import read_jsonl, write_jsonl
from src.actions import ActionProposal, ApprovalDecision, HumanApprovalWorkflow
from src.actions.store import ActionStore
from src.actions.workflow import WORKFLOW_VERSION as LANGGRAPH_WORKFLOW_VERSION
from src.runtime_compare import (
    AGENTS_SDK_WORKFLOW_VERSION,
    AgentsSDKApprovalWorkflow,
)

from .make_cases import validate_cases
from .replay_model import FrozenCouponToolCallModel


RUNTIMES = ("langgraph", "openai_agents_sdk")


def pct(numerator: int, denominator: int) -> float:
    return round(100 * numerator / denominator, 2) if denominator else 0.0


def mean(values: list[float]) -> float:
    return round(statistics.mean(values), 4) if values else 0.0


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(round((len(ordered) - 1) * quantile), len(ordered) - 1)
    return round(ordered[index], 4)


def decision_for(case: dict[str, Any], proposal: ActionProposal) -> ApprovalDecision:
    return ApprovalDecision(
        action_id=proposal.action_id,
        decision=case["decision"],
        reviewer_id=case["reviewer_id"],
        reason=case["decision_reason"],
    )


def expected_audit(case: dict[str, Any]) -> list[str]:
    return [
        "PROPOSED",
        "APPROVAL_REQUESTED",
        case["decision"],
        *(["EXECUTED"] if case["decision"] == "APPROVED" else []),
    ]


def evaluate_record(
    case: dict[str, Any],
    pending: Any,
    completed: Any,
    *,
    pre_decision_event_count: int,
    event_count: int,
    audit_events: list[str],
    failure_observed: bool,
) -> dict[str, Any]:
    approved = case["decision"] == "APPROVED"
    return {
        "approval_gated": (
            pending.status == "PENDING_APPROVAL"
            and pending.approval_request is not None
            and pre_decision_event_count == 0
        ),
        "correct_outcome": (
            completed.status == ("EXECUTED" if approved else "REJECTED")
            and event_count == (1 if approved else 0)
        ),
        "fully_audited": audit_events == expected_audit(case),
        "recovered": (
            not case["inject_post_commit_failure"] or failure_observed
        ),
        "duplicate_action": event_count > 1,
    }


def run_langgraph(case: dict[str, Any], runtime_dir: Path) -> dict[str, Any]:
    proposal = ActionProposal.model_validate(case["proposal"])
    started = time.perf_counter()
    with HumanApprovalWorkflow(runtime_dir) as workflow:
        pending = workflow.start(proposal)
        pre_decision_event_count = workflow.store.event_count(proposal.action_id)
    pending_seconds = time.perf_counter() - started
    pending_state_bytes = (runtime_dir / "checkpoints.sqlite3").stat().st_size

    failure_observed = False
    resumed = time.perf_counter()
    try:
        with HumanApprovalWorkflow(
            runtime_dir,
            fail_after_event_action_ids=(
                {proposal.action_id}
                if case["inject_post_commit_failure"]
                else set()
            ),
        ) as workflow:
            completed = workflow.decide(
                proposal.action_id,
                decision_for(case, proposal),
            )
    except RuntimeError as exc:
        if "injected failure after synthetic event commit" not in str(exc):
            raise
        failure_observed = True
        with HumanApprovalWorkflow(runtime_dir) as workflow:
            completed = workflow.recover(proposal.action_id)
    resume_seconds = time.perf_counter() - resumed
    with ActionStore(runtime_dir / "actions.sqlite3") as store:
        event_count = store.event_count(proposal.action_id)
        audit_events = store.audit_events(proposal.action_id)
    evaluation = evaluate_record(
        case,
        pending,
        completed,
        pre_decision_event_count=pre_decision_event_count,
        event_count=event_count,
        audit_events=audit_events,
        failure_observed=failure_observed,
    )
    return {
        "runtime": "langgraph",
        "case": case,
        **evaluation,
        "failure_observed": failure_observed,
        "event_count": event_count,
        "audit_events": audit_events,
        "pending_state_bytes": pending_state_bytes,
        "latency_ms": {
            "pending": round(pending_seconds * 1000, 4),
            "resume": round(resume_seconds * 1000, 4),
            "total": round((pending_seconds + resume_seconds) * 1000, 4),
        },
        "run": completed.model_dump(mode="json"),
    }


async def run_agents_sdk(
    case: dict[str, Any],
    runtime_dir: Path,
) -> dict[str, Any]:
    proposal = ActionProposal.model_validate(case["proposal"])
    started = time.perf_counter()
    pending = await AgentsSDKApprovalWorkflow(
        proposal,
        runtime_dir,
        model=FrozenCouponToolCallModel(proposal),
    ).start()
    with ActionStore(runtime_dir / "actions.sqlite3") as store:
        pre_decision_event_count = store.event_count(proposal.action_id)
    pending_seconds = time.perf_counter() - started
    pending_state_bytes = (runtime_dir / "run_state.json").stat().st_size

    failure_observed = False
    resumed = time.perf_counter()
    try:
        completed = await AgentsSDKApprovalWorkflow(
            proposal,
            runtime_dir,
            model=FrozenCouponToolCallModel(proposal),
            fail_after_event=case["inject_post_commit_failure"],
        ).decide(decision_for(case, proposal))
    except Exception as exc:
        if "injected failure after synthetic event commit" not in str(exc):
            raise
        failure_observed = True
        completed = await AgentsSDKApprovalWorkflow(
            proposal,
            runtime_dir,
            model=FrozenCouponToolCallModel(proposal),
        ).recover()
    resume_seconds = time.perf_counter() - resumed
    with ActionStore(runtime_dir / "actions.sqlite3") as store:
        event_count = store.event_count(proposal.action_id)
        audit_events = store.audit_events(proposal.action_id)
    evaluation = evaluate_record(
        case,
        pending,
        completed,
        pre_decision_event_count=pre_decision_event_count,
        event_count=event_count,
        audit_events=audit_events,
        failure_observed=failure_observed,
    )
    return {
        "runtime": "openai_agents_sdk",
        "case": case,
        **evaluation,
        "failure_observed": failure_observed,
        "event_count": event_count,
        "audit_events": audit_events,
        "pending_state_bytes": pending_state_bytes,
        "latency_ms": {
            "pending": round(pending_seconds * 1000, 4),
            "resume": round(resume_seconds * 1000, 4),
            "total": round((pending_seconds + resume_seconds) * 1000, 4),
        },
        "run": completed.model_dump(mode="json"),
    }


def count_source_lines(path: Path) -> int:
    return sum(
        bool(line.strip()) and not line.lstrip().startswith("#")
        for line in path.read_text(encoding="utf-8").splitlines()
    )


def summarize(runtime: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    selected = [record for record in records if record["runtime"] == runtime]
    recovery = [
        record
        for record in selected
        if record["case"]["inject_post_commit_failure"]
    ]
    total_latency = [record["latency_ms"]["total"] for record in selected]
    state_bytes = [float(record["pending_state_bytes"]) for record in selected]
    return {
        "cases": len(selected),
        "approval_gated_rate_pct": pct(
            sum(record["approval_gated"] for record in selected), len(selected)
        ),
        "correct_outcome_rate_pct": pct(
            sum(record["correct_outcome"] for record in selected), len(selected)
        ),
        "actions_audited_rate_pct": pct(
            sum(record["fully_audited"] for record in selected), len(selected)
        ),
        "state_recovery_rate_pct": pct(
            sum(record["recovered"] for record in recovery), len(recovery)
        ),
        "duplicate_action_rate_pct": pct(
            sum(record["duplicate_action"] for record in selected), len(selected)
        ),
        "latency_ms": {
            "mean": mean(total_latency),
            "p50": percentile(total_latency, 0.5),
            "p95": percentile(total_latency, 0.95),
        },
        "pending_state_bytes": {
            "mean": mean(state_bytes),
            "min": int(min(state_bytes)),
            "max": int(max(state_bytes)),
        },
    }


async def run_benchmark(
    cases: list[dict[str, Any]],
    runtime_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    validate_cases(cases)
    records = []
    for index, case in enumerate(cases, start=1):
        records.append(
            run_langgraph(case, runtime_root / "langgraph" / f"case-{index:02d}")
        )
        records.append(await run_agents_sdk(
            case,
            runtime_root / "agents-sdk" / f"case-{index:02d}",
        ))

    langgraph = summarize("langgraph", records)
    agents_sdk = summarize("openai_agents_sdk", records)
    parity_failures = [
        {
            "runtime": record["runtime"],
            "case_id": record["case"]["case_id"],
            "approval_gated": record["approval_gated"],
            "correct_outcome": record["correct_outcome"],
            "fully_audited": record["fully_audited"],
            "recovered": record["recovered"],
            "duplicate_action": record["duplicate_action"],
        }
        for record in records
        if not all((
            record["approval_gated"],
            record["correct_outcome"],
            record["fully_audited"],
            record["recovered"],
            not record["duplicate_action"],
        ))
    ]
    report = {
        "comparison_cases": len(cases),
        "runtime_executions": len(records),
        "external_model_api_calls": 0,
        "deterministic_model_replay_calls": len(cases) * 2,
        "runtimes": {
            "langgraph": {
                **langgraph,
                "workflow_version": LANGGRAPH_WORKFLOW_VERSION,
                "framework_version": "1.2.9",
                "implementation_source_lines": count_source_lines(
                    Path("src/actions/workflow.py")
                ),
            },
            "openai_agents_sdk": {
                **agents_sdk,
                "workflow_version": AGENTS_SDK_WORKFLOW_VERSION,
                "framework_version": agents.__version__,
                "openai_client_version": openai.__version__,
                "implementation_source_lines": count_source_lines(
                    Path("src/runtime_compare/agents_sdk.py")
                ),
            },
        },
        "behavioral_parity": not parity_failures,
        "qualitative_comparison": {
            "state": {
                "langgraph": "Typed graph state with automatic SQLite checkpoints.",
                "openai_agents_sdk": (
                    "Serializable RunState; the application chooses and manages storage."
                ),
            },
            "routing": {
                "langgraph": "Explicit named nodes and conditional edges.",
                "openai_agents_sdk": "Implicit model/tool runner loop.",
            },
            "tool_calls": {
                "langgraph": "Application-owned action node.",
                "openai_agents_sdk": "SDK-native function tool selected by model output.",
            },
            "human_approval": {
                "langgraph": "Application-defined interrupt payload and Command resume.",
                "openai_agents_sdk": (
                    "Tool needs_approval, interruption, RunState approve/reject."
                ),
            },
            "tracing": {
                "langgraph": "State history and explicit transition list.",
                "openai_agents_sdk": (
                    "Built-in trace spans; export disabled in deterministic benchmark."
                ),
            },
            "testability": {
                "langgraph": "Node methods and checkpoint snapshots are directly testable.",
                "openai_agents_sdk": (
                    "Custom Model enables deterministic Runner and approval tests."
                ),
            },
        },
        "experiment_design": (
            "Twenty frozen Commit 12 ISSUE_COUPON cases run through both runtimes. "
            "A deterministic model replay isolates orchestration and makes no API calls."
        ),
        "failures": parity_failures,
    }
    return records, report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("evals/commit13/cases.jsonl"),
    )
    parser.add_argument(
        "--results",
        type=Path,
        default=Path("evals/commit13/reports/runtime_results.jsonl"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("evals/commit13/reports/runtime_comparison.json"),
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    cases = read_jsonl(args.cases)
    with tempfile.TemporaryDirectory(prefix="signaldesk-commit13-") as tmp:
        records, report = await run_benchmark(cases, Path(tmp))
    report["run_config"] = {
        "cases_file": str(args.cases),
        "cases_sha256": hashlib.sha256(args.cases.read_bytes()).hexdigest(),
    }
    write_jsonl(args.results, records)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
