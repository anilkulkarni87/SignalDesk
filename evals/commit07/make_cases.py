#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.llm.customer_store import CustomerStore
from src.retrieval.query_planner import (
    combined_query,
    expected_doc_ids,
    expected_families,
    plan_policy_queries,
)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--database", required=True)
    p.add_argument(
        "--source-cases",
        type=Path,
        default=Path("evals/commit05/cases.jsonl"),
    )
    p.add_argument(
        "--output",
        type=Path,
        default=Path("evals/commit07/cases.jsonl"),
    )
    return p.parse_args()


def read_jsonl(path: str | Path):
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


QUESTION_VARIANTS = (
    (
        "risk_investigation",
        "Why is this customer's retention risk at its current level, and what "
        "should a specialist investigate next under current NovaCart policy?",
    ),
    (
        "policy_guardrails",
        "Which current policy constraints and known knowledge gaps should shape "
        "any retention recommendation for this customer?",
    ),
)


def build_cases(source_cases: list[dict], store: CustomerStore) -> list[dict]:
    cases = []
    for source_case in source_cases:
        snapshot = store.get_snapshot(source_case["customer_id"])
        planned_queries = plan_policy_queries(snapshot)
        for question_type, question in QUESTION_VARIANTS:
            cases.append({
                "rag_eval_version": "commit07_rag_v1_100_questions",
                "case_id": f'{source_case["case_id"]}__{question_type}',
                "source_case_id": source_case["case_id"],
                "source_case_type": source_case["case_type"],
                "customer_id": source_case["customer_id"],
                "question_type": question_type,
                "question": question,
                "retrieval_query": combined_query(snapshot),
                "planned_policy_queries": [
                    query.to_dict() for query in planned_queries
                ],
                "expected_risk_level": source_case["expected_risk_level"],
                "required_evidence_all": source_case.get(
                    "required_evidence_all",
                    [],
                ),
                "required_evidence_any": source_case.get(
                    "required_evidence_any",
                    [],
                ),
                "expected_policy_doc_ids_all": expected_doc_ids(snapshot),
                "expected_policy_families_all": expected_families(snapshot),
            })

    if len(source_cases) != 50 or len(cases) != 100:
        raise ValueError(
            f"Expected 50 source cases and 100 RAG questions; got "
            f"{len(source_cases)} and {len(cases)}"
        )
    return cases


def main():
    args = parse_args()
    store = CustomerStore(args.database)
    source_cases = list(read_jsonl(args.source_cases))
    cases = build_cases(source_cases, store)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        for case in cases:
            f.write(json.dumps(case) + "\n")

    print(json.dumps({
        "source_cases": str(args.source_cases),
        "output": str(args.output),
        "cases": len(cases),
        "source_customer_cases": len(source_cases),
        "questions_per_customer": len(QUESTION_VARIANTS),
    }, indent=2))


if __name__ == "__main__":
    main()
