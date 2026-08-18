#!/usr/bin/env python3

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from evals.commit12.make_cases import read_jsonl
from src.actions import ActionProposal, ApprovalDecision
from src.runtime_compare import AgentsSDKApprovalWorkflow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case-id",
        default="agent_multiple_warning_signals_01__approved",
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("evals/commit13/cases.jsonl"),
    )
    parser.add_argument(
        "--runtime-dir",
        type=Path,
        default=Path("data/runtime/commit13/agents-sdk-demo"),
    )
    parser.add_argument("--reviewer-id", default="local-human-reviewer")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    cases = {case["case_id"]: case for case in read_jsonl(args.cases)}
    try:
        case = cases[args.case_id]
    except KeyError as exc:
        raise SystemExit(f"Unknown coupon comparison case: {args.case_id}") from exc

    proposal = ActionProposal.model_validate(case["proposal"])
    workflow = AgentsSDKApprovalWorkflow(proposal, args.runtime_dir)
    run = await workflow.start()
    if run.status != "PENDING_APPROVAL":
        print(json.dumps(run.model_dump(mode="json"), indent=2))
        return

    request = run.approval_request
    print("\nOpenAI Agents SDK approval required\n")
    print(f"Action ID:       {request.action_id}")
    print(f"Customer:        {request.customer_id}")
    print(f"Recommendation:  {request.recommendation}")
    print(f"Reason:          {request.reason}")
    print(f"Expected impact: {request.expected_impact}")
    print("Exact SDK tool payload:")
    print(json.dumps(request.action.model_dump(mode="json"), indent=2))

    answer = input("\nApprove or reject? [approve/reject]: ").strip().lower()
    if answer not in {"approve", "reject"}:
        raise SystemExit("No decision recorded. Enter approve or reject.")
    reason = input("Decision reason: ").strip()
    completed = await workflow.decide(ApprovalDecision(
        action_id=proposal.action_id,
        decision="APPROVED" if answer == "approve" else "REJECTED",
        reviewer_id=args.reviewer_id,
        reason=reason,
    ))
    print("\nDecision recorded\n")
    print(json.dumps(completed.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
