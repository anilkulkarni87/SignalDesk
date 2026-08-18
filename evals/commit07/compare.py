#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path


COMPARISON_METRICS = (
    "api_success",
    "schema_valid",
    "risk_correct",
    "required_evidence_all_present",
    "required_evidence_any_present",
    "answer_correct",
    "expected_policy_docs_retrieved",
    "expected_policy_families_retrieved",
    "all_citations_retrieved",
    "all_citation_excerpts_grounded",
    "expected_policy_docs_cited",
    "expected_policy_families_cited",
    "unsupported_policy_claims_empty",
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/commit07/reports/compare_v3_vs_v6.json"),
    )
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def index_rows(rows: list[dict]) -> dict[str, dict]:
    indexed = {row["case"]["case_id"]: row for row in rows}
    if len(indexed) != len(rows):
        raise ValueError("Results contain duplicate case IDs")
    return indexed


def metric_transition(
    baseline: dict[str, dict],
    candidate: dict[str, dict],
    metric: str,
) -> dict:
    shared_ids = sorted(set(baseline) & set(candidate))
    improvements = [
        case_id
        for case_id in shared_ids
        if not baseline[case_id].get(metric, False)
        and candidate[case_id].get(metric, False)
    ]
    regressions = [
        case_id
        for case_id in shared_ids
        if baseline[case_id].get(metric, False)
        and not candidate[case_id].get(metric, False)
    ]
    return {
        "baseline_passed": sum(
            bool(baseline[case_id].get(metric)) for case_id in shared_ids
        ),
        "candidate_passed": sum(
            bool(candidate[case_id].get(metric)) for case_id in shared_ids
        ),
        "improvements": improvements,
        "regressions": regressions,
    }


def main():
    args = parse_args()
    baseline_rows = read_jsonl(args.baseline)
    candidate_rows = read_jsonl(args.candidate)
    baseline = index_rows(baseline_rows)
    candidate = index_rows(candidate_rows)
    shared_ids = sorted(set(baseline) & set(candidate))

    report = {
        "baseline_file": str(args.baseline),
        "candidate_file": str(args.candidate),
        "baseline_prompt_versions": sorted({
            row.get("prompt_version") for row in baseline_rows
        }),
        "candidate_prompt_versions": sorted({
            row.get("prompt_version") for row in candidate_rows
        }),
        "baseline_cases": len(baseline_rows),
        "candidate_cases": len(candidate_rows),
        "shared_cases": len(shared_ids),
        "missing_from_candidate": sorted(set(baseline) - set(candidate)),
        "new_in_candidate": sorted(set(candidate) - set(baseline)),
        "metrics": {
            metric: metric_transition(baseline, candidate, metric)
            for metric in COMPARISON_METRICS
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
