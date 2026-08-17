#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path


RUBRIC_VERSION = "commit05_eval_from_commit04_v2_selectors"


CASE_SPECS = (
    {
        "case_type": "multiple_warning_signals",
        # Commit 04 v2: require purchase decline plus at least one independent
        # warning domain, with ACTIVE status to avoid undefined status semantics.
        "expected_risk_level": "HIGH",
        "where": (
            "customer_status = 'ACTIVE' "
            "AND purchase_decline_flag "
            "AND (engagement_decline_flag OR support_attention_flag)"
        ),
    },
    {
        "case_type": "purchase_decline_only",
        "expected_risk_level": "MEDIUM",
        "where": (
            "customer_status = 'ACTIVE' "
            "AND purchase_decline_flag "
            "AND NOT engagement_decline_flag "
            "AND NOT support_attention_flag "
            "AND refund_rate_90d <= 0.25 "
            "AND NOT recent_subscription_cancellation_flag"
        ),
    },
    {
        "case_type": "engagement_decline_only",
        "expected_risk_level": "MEDIUM",
        "where": (
            "customer_status = 'ACTIVE' "
            "AND engagement_decline_flag "
            "AND NOT purchase_decline_flag "
            "AND NOT support_attention_flag "
            "AND orders_60d > 0 "
            "AND (purchase_change_pct IS NULL OR purchase_change_pct >= 0) "
            "AND refund_rate_90d <= 0.25 "
            "AND NOT recent_subscription_cancellation_flag"
        ),
    },
    {
        "case_type": "support_attention_only",
        "expected_risk_level": "MEDIUM",
        "where": (
            "customer_status = 'ACTIVE' "
            "AND support_attention_flag "
            "AND NOT purchase_decline_flag "
            "AND NOT engagement_decline_flag "
            "AND orders_60d > 0 "
            "AND days_since_purchase <= 90 "
            "AND sessions_60d > 0 "
            "AND refund_rate_90d <= 0.25 "
            "AND NOT recent_subscription_cancellation_flag "
            "AND open_support_cases = 1 "
            "AND negative_support_cases_90d <= 1 "
            "AND high_priority_support_cases_90d = 0"
        ),
    },
    {
        "case_type": "no_warning_signals",
        "expected_risk_level": "LOW",
        "where": (
            "customer_status = 'ACTIVE' "
            "AND NOT purchase_decline_flag "
            "AND NOT engagement_decline_flag "
            "AND NOT support_attention_flag "
            "AND orders_60d > 0 "
            "AND sessions_60d > 0 "
            "AND days_since_purchase <= 60 "
            "AND refund_rate_90d = 0 "
            "AND NOT recent_subscription_cancellation_flag"
        ),
    },
)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--database", required=True)
    p.add_argument(
        "--output",
        type=Path,
        default=Path("evals/commit05/cases.jsonl"),
    )
    p.add_argument("--cases-per-type", type=int, default=10)
    return p.parse_args()


def expected_evidence(case_type: str, row: dict) -> list[str]:
    if case_type == "multiple_warning_signals":
        return [
            name for name in (
                "purchase_decline_flag",
                "engagement_decline_flag",
                "support_attention_flag",
            )
            if row[name]
        ]

    mapping = {
        "purchase_decline_only": ["purchase_decline_flag"],
        "engagement_decline_only": ["engagement_decline_flag"],
        "support_attention_only": ["support_attention_flag"],
        "no_warning_signals": [],
    }
    return mapping[case_type]


def main():
    args = parse_args()

    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError("Install DuckDB: pip install duckdb") from exc

    con = duckdb.connect(args.database, read_only=True)
    cases = []
    availability = {}

    for spec in CASE_SPECS:
        selected_rows = con.execute(
                f"""
                SELECT
                    customer_id,
                    purchase_decline_flag,
                    engagement_decline_flag,
                    support_attention_flag
                FROM customer_360
                WHERE {spec["where"]}
                ORDER BY hash(customer_id)
                LIMIT ?
                """,
                [args.cases_per_type],
            ).fetchall()

        availability[spec["case_type"]] = len(selected_rows)

        if len(selected_rows) < args.cases_per_type:
            raise RuntimeError(
                f"Only found {len(selected_rows)} clean {spec['case_type']} "
                f"cases; need {args.cases_per_type}. Review the selector "
                "instead of weakening the rubric."
            )

        columns = [d[0] for d in con.description]

        for index, values in enumerate(selected_rows, start=1):
            row = dict(zip(columns, values))
            cases.append({
                "rubric_version": RUBRIC_VERSION,
                "case_id": f"{spec['case_type']}_{index:02d}",
                "case_type": spec["case_type"],
                "customer_id": row["customer_id"],
                "expected_risk_level": spec["expected_risk_level"],
                "required_evidence_all": expected_evidence(
                    spec["case_type"],
                    row,
                ),
                "required_evidence_any": [],
            })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        for row in cases:
            f.write(json.dumps(row) + "\n")

    print(json.dumps({
        "rubric_version": RUBRIC_VERSION,
        "cases": len(cases),
        "cases_per_type": args.cases_per_type,
        "availability_selected": availability,
        "output": str(args.output),
        "note": (
            "Uses Commit 04 eval v2 selectors to avoid contradictory broader "
            "Customer 360 evidence while expanding to 10 cases per category."
        ),
    }, indent=2))


if __name__ == "__main__":
    main()
