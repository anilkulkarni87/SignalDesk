#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from src.actions import (
    AccountFlagAction,
    ActionProposal,
    CampaignEnrollmentAction,
    CouponAction,
    RetentionOfferAction,
    SupportCaseAction,
)


CASE_VERSION = "commit12_v1_frozen_approval_boundary"
DECISIONS = ("APPROVED", "REJECTED")
ACTION_TYPES = (
    "ISSUE_COUPON",
    "ENROLL_CAMPAIGN",
    "CREATE_SUPPORT_CASE",
    "FLAG_ACCOUNT",
    "SEND_RETENTION_OFFER",
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _action(action_type: str, index: int):
    suffix = f"{index + 1:03d}"
    if action_type == "ISSUE_COUPON":
        return CouponAction(
            coupon_code=f"LEARN{suffix}",
            discount_percent=10,
            expires_in_days=30,
        )
    if action_type == "ENROLL_CAMPAIGN":
        return CampaignEnrollmentAction(
            campaign_id=f"CMP-LEARN{suffix}",
            channel="EMAIL",
        )
    if action_type == "CREATE_SUPPORT_CASE":
        return SupportCaseAction(
            priority="HIGH",
            summary=f"Review the bounded investigation for frozen case {suffix}.",
        )
    if action_type == "FLAG_ACCOUNT":
        return AccountFlagAction(
            flag_code="RETENTION_RISK",
            reason=f"Human review requested by frozen learning case {suffix}.",
        )
    if action_type == "SEND_RETENTION_OFFER":
        return RetentionOfferAction(
            offer_id=f"OFFER-LEARN{suffix}",
            channel="EMAIL",
        )
    raise ValueError(f"Unknown action type: {action_type}")


def build_cases(source_cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(source_cases) != 50:
        raise ValueError(f"Expected 50 frozen Commit 10 cases, found {len(source_cases)}")
    cases = []
    for index, source in enumerate(source_cases):
        action_type = ACTION_TYPES[index % len(ACTION_TYPES)]
        for decision in DECISIONS:
            variant = decision.lower()
            source_reference = f"{source['case_id']}__{variant}"
            proposal = ActionProposal.build(
                customer_id=source["customer_id"],
                action=_action(action_type, index),
                recommendation=(
                    f"Submit {action_type} for human authorization in the "
                    "synthetic learning environment."
                ),
                reason=(
                    f"The accepted investigation {source['case_id']} supplies the "
                    "customer context; action quality is outside this experiment."
                ),
                expected_impact=(
                    "A synthetic CDP event is written only if a reviewer approves "
                    "the exact payload."
                ),
                source_case_id=source_reference,
            )
            cases.append({
                "case_id": source_reference,
                "case_version": CASE_VERSION,
                "source_case_id": source["case_id"],
                "source_task_type": source["task_type"],
                "customer_id": source["customer_id"],
                "proposal": proposal.model_dump(mode="json"),
                "decision": decision,
                "reviewer_id": "commit12-human-reviewer",
                "decision_reason": (
                    "Approved exact synthetic payload for the frozen experiment."
                    if decision == "APPROVED"
                    else "Rejected exact synthetic payload for the frozen experiment."
                ),
                "inject_post_commit_failure": (
                    decision == "APPROVED" and index % 2 == 0
                ),
            })
    return cases


def validate_cases(cases: list[dict[str, Any]]) -> None:
    if len(cases) != 100:
        raise ValueError(f"Expected 100 approval cases, found {len(cases)}")
    if len({case["case_id"] for case in cases}) != 100:
        raise ValueError("Approval case IDs must be unique")
    if len({case["proposal"]["action_id"] for case in cases}) != 100:
        raise ValueError("Action IDs must be unique")
    if {case["decision"] for case in cases} != set(DECISIONS):
        raise ValueError("Both approval decisions are required")
    if sum(case["decision"] == "APPROVED" for case in cases) != 50:
        raise ValueError("Expected 50 approved cases")
    if sum(case["decision"] == "REJECTED" for case in cases) != 50:
        raise ValueError("Expected 50 rejected cases")
    counts = {
        action_type: sum(
            case["proposal"]["action"]["action_type"] == action_type
            for case in cases
        )
        for action_type in ACTION_TYPES
    }
    if set(counts.values()) != {20}:
        raise ValueError(f"Expected 20 cases per action type, found {counts}")
    source_counts = {
        case_id: sum(case["source_case_id"] == case_id for case in cases)
        for case_id in {case["source_case_id"] for case in cases}
    }
    if len(source_counts) != 50 or set(source_counts.values()) != {2}:
        raise ValueError("Each source customer case must have approve and reject cases")
    for case in cases:
        ActionProposal.model_validate(case["proposal"])


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-cases",
        type=Path,
        default=Path("evals/commit10/cases.jsonl"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/commit12/cases.jsonl"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases = build_cases(read_jsonl(args.source_cases))
    validate_cases(cases)
    write_jsonl(args.output, cases)
    print(json.dumps({
        "cases": len(cases),
        "case_version": CASE_VERSION,
        "source_cases_sha256": hashlib.sha256(
            args.source_cases.read_bytes()
        ).hexdigest(),
        "output": str(args.output),
    }, indent=2))


if __name__ == "__main__":
    main()
