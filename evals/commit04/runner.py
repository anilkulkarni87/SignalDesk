#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from src.llm.client import SignalDeskLLMClient
from src.llm.customer_store import CustomerStore


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--database", required=True)
    p.add_argument(
        "--cases",
        type=Path,
        default=Path("evals/commit04/cases_v2.jsonl"),
    )
    p.add_argument(
        "--output",
        type=Path,
        default=Path("evals/commit04/results_luna_none_v2.jsonl"),
    )
    p.add_argument("--model", default=None)
    p.add_argument(
        "--reasoning-effort",
        default="none",
        choices=["none", "low", "medium", "high", "xhigh", "max"],
    )
    p.add_argument("--sleep-seconds", type=float, default=0.0)
    return p.parse_args()


def read_jsonl(path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def main():
    args = parse_args()

    store = CustomerStore(args.database)
    client = SignalDeskLLMClient(
        model=args.model,
        reasoning_effort=args.reasoning_effort,
    )

    cases = list(read_jsonl(args.cases))
    args.output.parent.mkdir(parents=True, exist_ok=True)

    passed_calls = 0

    with args.output.open("w", encoding="utf-8") as out:
        for index, case in enumerate(cases, start=1):
            record = {
                "case": case,
                "schema_valid": False,
                "api_success": False,
            }

            try:
                snapshot = store.get_snapshot(case["customer_id"])
                result = client.assess(snapshot)
                assessment = result.assessment

                cited = {item.feature for item in assessment.evidence}
                required_all = set(case.get("required_evidence_all", []))
                required_any = set(case.get("required_evidence_any", []))

                required_all_present = required_all.issubset(cited)
                required_any_present = (
                    True if not required_any else bool(cited & required_any)
                )

                record.update({
                    "api_success": True,
                    "schema_valid": True,
                    "snapshot": snapshot,
                    "assessment": assessment.model_dump(),
                    "metrics": result.to_dict()["metrics"],
                    "risk_correct": (
                        assessment.risk_level == case["expected_risk_level"]
                    ),
                    "required_evidence_all_present": required_all_present,
                    "required_evidence_any_present": required_any_present,
                    "required_evidence_present": (
                        required_all_present and required_any_present
                    ),
                    "evidence_features_valid": all(
                        feature in snapshot for feature in cited
                    ),
                })
                passed_calls += 1

            except Exception as exc:
                record["error_type"] = type(exc).__name__
                record["error"] = str(exc)

            out.write(json.dumps(record, default=str) + "\n")
            out.flush()

            print(
                f'[{index:02d}/{len(cases)}] {case["case_id"]}: '
                f'{"OK" if record["api_success"] else "ERROR"}'
            )

            if args.sleep_seconds > 0:
                time.sleep(args.sleep_seconds)

    print(json.dumps({
        "cases": len(cases),
        "successful_api_calls": passed_calls,
        "output": str(args.output),
    }, indent=2))


if __name__ == "__main__":
    main()
