#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .metrics import EVALUATION_VERSION, build_report, evaluate_case
from .runner import read_case_ids, read_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--results",
        type=Path,
        default=Path("evals/commit10/reports/agent_results.jsonl"),
    )
    parser.add_argument(
        "--case-id-file",
        type=Path,
        default=Path("evals/commit10/v3_cohort_case_ids.txt"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("evals/commit10/reports/v2_cohort_regraded_report.json"),
    )
    return parser.parse_args()


def regrade_rows(
    rows: list[dict[str, Any]],
    requested_ids: list[str],
) -> list[dict[str, Any]]:
    requested = set(requested_ids)
    selected = [row for row in rows if row["case"]["case_id"] in requested]
    found = {row["case"]["case_id"] for row in selected}
    missing = requested - found
    if missing:
        raise ValueError(f"Case IDs missing from stored results: {sorted(missing)}")
    for row in selected:
        row["evaluation"] = (
            evaluate_case(row["case"], row["run"])
            if row.get("api_success")
            else {}
        )
    return selected


def main() -> None:
    args = parse_args()
    requested_ids = read_case_ids(args.case_id_file)
    rows = regrade_rows(read_jsonl(args.results), requested_ids)
    report = build_report(rows)
    report["run_config"] = {
        "source_results": str(args.results),
        "case_id_file": str(args.case_id_file),
        "evaluation_version": EVALUATION_VERSION,
        "source_prompt_versions": sorted({
            row["run"]["metrics"]["prompt_version"]
            for row in rows
            if row.get("api_success")
        }),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
