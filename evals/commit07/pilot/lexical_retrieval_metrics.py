#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.retrieval.lexical import search


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--cases",
        type=Path,
        default=Path("evals/commit07/pilot/lexical_retrieval_cases_7.jsonl"),
    )
    p.add_argument("--corpus-dir", default="data/generated/knowledge")
    p.add_argument("--top-k", type=int, default=3)
    p.add_argument(
        "--report",
        type=Path,
        default=Path("evals/commit07/pilot/lexical_retrieval_report_7.json"),
    )
    return p.parse_args()


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def pct(n: int, d: int) -> float:
    return round(100 * n / d, 2) if d else 0.0


def evaluate_case(case: dict, corpus_dir: str, top_k: int) -> dict:
    results = search(
        case["query"],
        corpus_dir=corpus_dir,
        top_k=top_k,
        statuses={"CURRENT"},
        authority={"APPROVED"},
    )
    retrieved_ids = [r.document_id for r in results]
    retrieved_families = [r.family for r in results]
    retrieved_statuses = [r.status for r in results]
    retrieved_authorities = [r.authority for r in results]
    expected = set(case.get("expected_doc_ids_all", []))
    forbidden = set(case.get("forbidden_doc_ids", []))
    expected_families = set(case.get("expected_families_any", []))
    forbidden_statuses = set(case.get("forbidden_statuses", []))

    expected_present = expected.issubset(retrieved_ids)
    expected_family_present = (
        True if not expected_families else bool(expected_families & set(retrieved_families))
    )
    expected_top_family_present = (
        True
        if "expected_top_family" not in case
        else bool(results) and results[0].family == case["expected_top_family"]
    )
    expected_status_present = (
        True
        if "expected_status" not in case
        else all(status == case["expected_status"] for status in retrieved_statuses)
    )
    expected_authority_present = (
        True
        if "expected_authority" not in case
        else all(
            authority == case["expected_authority"]
            for authority in retrieved_authorities
        )
    )
    forbidden_absent = not bool(forbidden & set(retrieved_ids))
    forbidden_statuses_absent = not bool(
        forbidden_statuses & set(retrieved_statuses)
    )
    excerpts_present = all(bool(r.excerpt.strip()) for r in results)

    return {
        "case_id": case["case_id"],
        "query": case["query"],
        "retrieved_doc_ids": retrieved_ids,
        "retrieved_families": retrieved_families,
        "retrieved_statuses": retrieved_statuses,
        "retrieved_authorities": retrieved_authorities,
        "expected_doc_ids_all": sorted(expected),
        "expected_families_any": sorted(expected_families),
        "forbidden_doc_ids": sorted(forbidden),
        "forbidden_statuses": sorted(forbidden_statuses),
        "expected_present": expected_present,
        "expected_family_present": expected_family_present,
        "expected_top_family_present": expected_top_family_present,
        "expected_status_present": expected_status_present,
        "expected_authority_present": expected_authority_present,
        "forbidden_absent": forbidden_absent,
        "forbidden_statuses_absent": forbidden_statuses_absent,
        "excerpts_present": excerpts_present,
        "passed": (
            expected_present
            and expected_family_present
            and expected_top_family_present
            and expected_status_present
            and expected_authority_present
            and forbidden_absent
            and forbidden_statuses_absent
            and excerpts_present
        ),
        "results": [r.to_dict() for r in results],
    }


def build_report(cases: list[dict], corpus_dir: str, top_k: int) -> dict:
    case_reports = [
        evaluate_case(case, corpus_dir, top_k)
        for case in cases
    ]
    passed = sum(r["passed"] for r in case_reports)
    expected_present = sum(r["expected_present"] for r in case_reports)
    expected_family_present = sum(
        r["expected_family_present"] for r in case_reports
    )
    expected_top_family_present = sum(
        r["expected_top_family_present"] for r in case_reports
    )
    expected_status_present = sum(
        r["expected_status_present"] for r in case_reports
    )
    expected_authority_present = sum(
        r["expected_authority_present"] for r in case_reports
    )
    forbidden_absent = sum(r["forbidden_absent"] for r in case_reports)
    forbidden_statuses_absent = sum(
        r["forbidden_statuses_absent"] for r in case_reports
    )
    excerpts_present = sum(r["excerpts_present"] for r in case_reports)

    return {
        "cases": len(case_reports),
        "top_k": top_k,
        "corpus_dir": corpus_dir,
        "passed": passed,
        "pass_rate_pct": pct(passed, len(case_reports)),
        "expected_doc_id_present_rate_pct": pct(
            expected_present,
            len(case_reports),
        ),
        "expected_family_present_rate_pct": pct(
            expected_family_present,
            len(case_reports),
        ),
        "expected_top_family_rate_pct": pct(
            expected_top_family_present,
            len(case_reports),
        ),
        "expected_status_rate_pct": pct(
            expected_status_present,
            len(case_reports),
        ),
        "expected_authority_rate_pct": pct(
            expected_authority_present,
            len(case_reports),
        ),
        "forbidden_absent_rate_pct": pct(forbidden_absent, len(case_reports)),
        "forbidden_statuses_absent_rate_pct": pct(
            forbidden_statuses_absent,
            len(case_reports),
        ),
        "excerpts_present_rate_pct": pct(excerpts_present, len(case_reports)),
        "case_reports": case_reports,
    }


def main():
    args = parse_args()
    cases = list(read_jsonl(args.cases))
    report = build_report(cases, args.corpus_dir, args.top_k)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

    if report["pass_rate_pct"] < 100:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
