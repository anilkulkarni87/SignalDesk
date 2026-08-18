#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from src.actions import ActionProposal, ApprovalDecision, HumanApprovalWorkflow
from src.actions.workflow import WORKFLOW_VERSION

from .make_cases import read_jsonl, validate_cases, write_jsonl


def pct(numerator: int, denominator: int) -> float:
    return round(100 * numerator / denominator, 2) if denominator else 0.0


def run_case(case: dict[str, Any], runtime_dir: Path) -> dict[str, Any]:
    proposal = ActionProposal.model_validate(case["proposal"])
    thread_id = proposal.action_id
    with HumanApprovalWorkflow(runtime_dir) as workflow:
        pending = workflow.start(proposal, thread_id=thread_id)
        approval_gated = (
            pending.status == "PENDING_APPROVAL"
            and pending.approval_request is not None
            and pending.approval_request.action == proposal.action
            and workflow.store.event_count(proposal.action_id) == 0
        )

    injected_failure_observed = False
    decision = ApprovalDecision(
        action_id=proposal.action_id,
        decision=case["decision"],
        reviewer_id=case["reviewer_id"],
        reason=case["decision_reason"],
    )
    fail_ids = (
        {proposal.action_id} if case["inject_post_commit_failure"] else set()
    )
    try:
        with HumanApprovalWorkflow(
            runtime_dir,
            fail_after_event_action_ids=fail_ids,
        ) as workflow:
            run = workflow.decide(thread_id, decision)
    except RuntimeError as exc:
        if "injected failure after synthetic event commit" not in str(exc):
            raise
        injected_failure_observed = True
        with HumanApprovalWorkflow(runtime_dir) as workflow:
            run = workflow.recover(thread_id)

    with HumanApprovalWorkflow(runtime_dir) as workflow:
        event_count = workflow.store.event_count(proposal.action_id)
        audit_events = workflow.store.audit_events(proposal.action_id)
        stored_decision = workflow.store.decision_for(proposal.action_id)

    approved = case["decision"] == "APPROVED"
    expected_audit = [
        "PROPOSED",
        "APPROVAL_REQUESTED",
        case["decision"],
        *(["EXECUTED"] if approved else []),
    ]
    recovered = (
        not case["inject_post_commit_failure"]
        or injected_failure_observed
    )
    correct_outcome = (
        run.status == ("EXECUTED" if approved else "REJECTED")
        and event_count == (1 if approved else 0)
        and stored_decision == case["decision"]
    )
    return {
        "case": case,
        "approval_gated": approval_gated,
        "correct_outcome": correct_outcome,
        "fully_audited": audit_events == expected_audit,
        "recovered": recovered,
        "injected_failure_observed": injected_failure_observed,
        "event_count": event_count,
        "duplicate_action": event_count > 1,
        "audit_events": audit_events,
        "run": run.model_dump(mode="json"),
    }


def run_benchmark(
    cases: list[dict[str, Any]],
    *,
    runtime_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    validate_cases(cases)
    records = []
    for index, case in enumerate(cases):
        records.append(run_case(case, runtime_root / f"case-{index + 1:03d}"))

    recovery_rows = [
        record
        for record in records
        if record["case"]["inject_post_commit_failure"]
    ]
    approved_rows = [
        record for record in records if record["case"]["decision"] == "APPROVED"
    ]
    rejected_rows = [
        record for record in records if record["case"]["decision"] == "REJECTED"
    ]
    action_counts = Counter(
        record["case"]["proposal"]["action"]["action_type"]
        for record in records
    )
    failures = [
        {
            "case_id": record["case"]["case_id"],
            "approval_gated": record["approval_gated"],
            "correct_outcome": record["correct_outcome"],
            "fully_audited": record["fully_audited"],
            "recovered": record["recovered"],
            "event_count": record["event_count"],
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
        "cases": len(records),
        "approved_cases": len(approved_rows),
        "rejected_cases": len(rejected_rows),
        "action_type_counts": dict(sorted(action_counts.items())),
        "approval_gated_rate_pct": pct(
            sum(record["approval_gated"] for record in records),
            len(records),
        ),
        "correct_outcome_rate_pct": pct(
            sum(record["correct_outcome"] for record in records),
            len(records),
        ),
        "actions_audited_rate_pct": pct(
            sum(record["fully_audited"] for record in records),
            len(records),
        ),
        "state_recovery_rate_pct": pct(
            sum(record["recovered"] for record in recovery_rows),
            len(recovery_rows),
        ),
        "injected_post_commit_failures": len(recovery_rows),
        "approved_action_execution_rate_pct": pct(
            sum(record["event_count"] == 1 for record in approved_rows),
            len(approved_rows),
        ),
        "rejected_action_non_execution_rate_pct": pct(
            sum(record["event_count"] == 0 for record in rejected_rows),
            len(rejected_rows),
        ),
        "duplicate_action_rate_pct": pct(
            sum(record["duplicate_action"] for record in records),
            len(records),
        ),
        "workflow_version": WORKFLOW_VERSION,
        "investigation_model": "gpt-5.6-luna",
        "investigation_reasoning_effort": "none",
        "model_calls_in_authorization_benchmark": 0,
        "experiment_design": (
            "Fifty accepted Commit 10 customer cases, each paired with one approve "
            "and one reject decision. This deterministic benchmark measures "
            "authorization, persistence, auditability, recovery, and idempotency; "
            "it does not measure action recommendation quality."
        ),
        "failures": failures,
    }
    return records, report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("evals/commit12/cases.jsonl"),
    )
    parser.add_argument(
        "--results",
        type=Path,
        default=Path("evals/commit12/reports/action_results.jsonl"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("evals/commit12/reports/action_report.json"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases = read_jsonl(args.cases)
    with tempfile.TemporaryDirectory(prefix="signaldesk-commit12-") as tmp:
        records, report = run_benchmark(cases, runtime_root=Path(tmp))
    report["run_config"] = {
        "cases_file": str(args.cases),
        "cases_sha256": hashlib.sha256(args.cases.read_bytes()).hexdigest(),
    }
    write_jsonl(args.results, records)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
