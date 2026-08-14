#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json

from src.llm.client import SignalDeskLLMClient
from src.llm.customer_store import CustomerStore


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--database", required=True)
    p.add_argument("--customer-id", required=True)
    p.add_argument("--model", default=None)
    p.add_argument(
        "--reasoning-effort",
        default="none",
        choices=["none", "low", "medium", "high", "xhigh", "max"],
    )
    return p.parse_args()


def main():
    args = parse_args()

    store = CustomerStore(args.database)
    snapshot = store.get_snapshot(args.customer_id)

    client = SignalDeskLLMClient(
        model=args.model,
        reasoning_effort=args.reasoning_effort,
    )

    result = client.assess(snapshot)

    # Application code resolves cited feature values deterministically.
    rendered_evidence = [
        {
            "feature": item.feature,
            "value": snapshot[item.feature],
            "interpretation": item.interpretation,
        }
        for item in result.assessment.evidence
    ]

    print(json.dumps({
        "customer_id": args.customer_id,
        "assessment": result.assessment.model_dump(),
        "rendered_evidence": rendered_evidence,
        "metrics": result.to_dict()["metrics"],
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
