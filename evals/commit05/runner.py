#!/usr/bin/env python3

from __future__ import annotations

import argparse
import importlib
import json
import time
from pathlib import Path

import src.llm.client as client_module
from src.llm.client import SignalDeskLLMClient
from src.llm.customer_store import CustomerStore


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--database", required=True)
    p.add_argument(
        "--cases",
        type=Path,
        default=Path("evals/commit05/cases.jsonl"),
    )
    p.add_argument(
        "--prompt-version",
        default="v1",
        choices=["v1", "v2"],
    )
    p.add_argument("--model", default="gpt-5.6-luna")
    p.add_argument(
        "--reasoning-effort",
        default="none",
        choices=["none", "low", "medium", "high", "xhigh", "max"],
    )
    p.add_argument("--sleep-seconds", type=float, default=0.0)
    p.add_argument("--output", type=Path, default=None)
    return p.parse_args()


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def install_prompt(prompt_version: str):
    prompt = importlib.import_module(f"src.llm.prompt_versions.{prompt_version}")

    # SignalDeskLLMClient imports prompt symbols into its module namespace.
    # Patch that namespace so Commit 05 can compare prompt versions without
    # rewriting the Commit 04 client.
    client_module.PROMPT_VERSION = prompt.PROMPT_VERSION
    client_module.SYSTEM_INSTRUCTIONS = prompt.SYSTEM_INSTRUCTIONS
    client_module.build_user_input = prompt.build_user_input
    return prompt


def default_output_path(prompt_version: str, model: str, reasoning_effort: str) -> Path:
    model_slug = model.replace(".", "_").replace("-", "_")
    return Path(
        "evals/commit05/reports/"
        f"results_{prompt_version}_{model_slug}_{reasoning_effort}.jsonl"
    )


def main():
    args = parse_args()
    prompt = install_prompt(args.prompt_version)
    output = args.output or default_output_path(
        args.prompt_version,
        args.model,
        args.reasoning_effort,
    )

    store = CustomerStore(args.database)
    client = SignalDeskLLMClient(
        model=args.model,
        reasoning_effort=args.reasoning_effort,
    )

    cases = list(read_jsonl(args.cases))
    output.parent.mkdir(parents=True, exist_ok=True)
    successful_api_calls = 0

    with output.open("w", encoding="utf-8") as out:
        for index, case in enumerate(cases, start=1):
            record = {
                "case": case,
                "prompt_version": prompt.PROMPT_VERSION,
                "prompt_change_hypothesis": prompt.PROMPT_CHANGE_HYPOTHESIS,
                "run_config": {
                    "model": args.model,
                    "reasoning_effort": args.reasoning_effort,
                },
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
                    "missing_required_evidence": sorted(required_all - cited),
                    "evidence_features_valid": all(
                        feature in snapshot for feature in cited
                    ),
                })
                successful_api_calls += 1
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
        "successful_api_calls": successful_api_calls,
        "prompt_version": prompt.PROMPT_VERSION,
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "output": str(output),
    }, indent=2))


if __name__ == "__main__":
    main()
