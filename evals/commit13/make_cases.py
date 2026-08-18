#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from evals.commit12.make_cases import read_jsonl, write_jsonl
from src.actions import ActionProposal


CASE_VERSION = "commit13_v1_fixed_coupon_runtime_comparison"


def build_cases(commit12_cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = [
        {
            **case,
            "comparison_case_version": CASE_VERSION,
        }
        for case in commit12_cases
        if case["proposal"]["action"]["action_type"] == "ISSUE_COUPON"
    ]
    return selected


def validate_cases(cases: list[dict[str, Any]]) -> None:
    if len(cases) != 20:
        raise ValueError(f"Expected 20 coupon cases, found {len(cases)}")
    if len({case["case_id"] for case in cases}) != 20:
        raise ValueError("Comparison case IDs must be unique")
    if len({case["source_case_id"] for case in cases}) != 10:
        raise ValueError("Expected ten source customer investigations")
    if sum(case["decision"] == "APPROVED" for case in cases) != 10:
        raise ValueError("Expected ten approved cases")
    if sum(case["decision"] == "REJECTED" for case in cases) != 10:
        raise ValueError("Expected ten rejected cases")
    if sum(case["inject_post_commit_failure"] for case in cases) != 5:
        raise ValueError("Expected five approved post-commit failures")
    for case in cases:
        if case["comparison_case_version"] != CASE_VERSION:
            raise ValueError("Comparison case version mismatch")
        proposal = ActionProposal.model_validate(case["proposal"])
        if proposal.action.action_type != "ISSUE_COUPON":
            raise ValueError("Comparison includes a non-coupon proposal")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-cases",
        type=Path,
        default=Path("evals/commit12/cases.jsonl"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/commit13/cases.jsonl"),
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
