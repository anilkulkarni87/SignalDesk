#!/usr/bin/env python3
"""Create Commit 04 evaluation rubric v2.

Why v2 exists:
The first rubric classified cases from only three boolean flags while the LLM
saw many other warning/positive features. That produced ambiguous "errors":
for example a support-only case could also be 220 days since purchase.

V2 deliberately selects cleaner cases whose broader Customer 360 evidence is
consistent with the expected risk label.

These labels remain an evaluation rubric, NOT a churn model.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


RUBRIC_VERSION = "commit04_eval_v2"

SEGMENTS = [
    {
        "case_type": "multiple_warning_signals",
        # Require purchase decline plus at least one independent warning domain.
        # ACTIVE removes undefined CLOSED/PAUSED status semantics from the case.
        "where": """
            customer_status = 'ACTIVE'
            AND purchase_decline_flag
            AND (engagement_decline_flag OR support_attention_flag)
        """,
        "expected_risk_level": "HIGH",
    },
    {
        "case_type": "purchase_decline_only",
        "where": """
            customer_status = 'ACTIVE'
            AND purchase_decline_flag
            AND NOT engagement_decline_flag
            AND NOT support_attention_flag
            AND refund_rate_90d <= 0.25
            AND NOT recent_subscription_cancellation_flag
        """,
        "expected_risk_level": "MEDIUM",
    },
    {
        "case_type": "engagement_decline_only",
        # Positive/nondeclining purchase evidence avoids a hidden purchase warning.
        "where": """
            customer_status = 'ACTIVE'
            AND engagement_decline_flag
            AND NOT purchase_decline_flag
            AND NOT support_attention_flag
            AND orders_60d > 0
            AND (purchase_change_pct IS NULL OR purchase_change_pct >= 0)
            AND refund_rate_90d <= 0.25
            AND NOT recent_subscription_cancellation_flag
        """,
        "expected_risk_level": "MEDIUM",
    },
    {
        "case_type": "support_attention_only",
        # Keep the support concern material but moderate and remove dormant /
        # refund / cancellation contradictions that caused v1 ambiguity.
        "where": """
            customer_status = 'ACTIVE'
            AND support_attention_flag
            AND NOT purchase_decline_flag
            AND NOT engagement_decline_flag
            AND orders_60d > 0
            AND days_since_purchase <= 90
            AND sessions_60d > 0
            AND refund_rate_90d <= 0.25
            AND NOT recent_subscription_cancellation_flag
            AND open_support_cases = 1
            AND negative_support_cases_90d <= 1
            AND high_priority_support_cases_90d = 0
        """,
        "expected_risk_level": "MEDIUM",
    },
    {
        "case_type": "no_warning_signals",
        # LOW should actually be low across the broader snapshot, not merely
        # "all three flags false."
        "where": """
            customer_status = 'ACTIVE'
            AND NOT purchase_decline_flag
            AND NOT engagement_decline_flag
            AND NOT support_attention_flag
            AND orders_60d > 0
            AND sessions_60d > 0
            AND days_since_purchase <= 60
            AND refund_rate_90d = 0
            AND NOT recent_subscription_cancellation_flag
        """,
        "expected_risk_level": "LOW",
    },
]


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--database", required=True)
    p.add_argument(
        "--output",
        type=Path,
        default=Path("evals/commit04/cases_v2.jsonl"),
    )
    p.add_argument("--per-type", type=int, default=6)
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
    import duckdb

    con = duckdb.connect(args.database, read_only=True)
    cases = []
    availability = {}

    for spec in SEGMENTS:
        rows = con.execute(
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
            [args.per_type],
        ).fetchall()

        availability[spec["case_type"]] = len(rows)

        if len(rows) < args.per_type:
            raise RuntimeError(
                f'Only {len(rows)} unambiguous rows available for '
                f'{spec["case_type"]}; need {args.per_type}. '
                f'Review the selector instead of silently weakening the rubric.'
            )

        columns = [d[0] for d in con.description]

        for idx, values in enumerate(rows, start=1):
            row = dict(zip(columns, values))
            cases.append({
                "rubric_version": RUBRIC_VERSION,
                "case_id": f'{spec["case_type"]}_{idx:02d}',
                "case_type": spec["case_type"],
                "customer_id": row["customer_id"],
                "expected_risk_level": spec["expected_risk_level"],
                "required_evidence_all": expected_evidence(
                    spec["case_type"], row
                ),
            })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        for case in cases:
            f.write(json.dumps(case) + "\n")

    print(json.dumps({
        "rubric_version": RUBRIC_VERSION,
        "cases": len(cases),
        "availability_selected": availability,
        "output": str(args.output),
        "note": (
            "V2 removes contradictory/undefined warning evidence from the "
            "single-signal and LOW categories. It remains an eval rubric, "
            "not a churn model."
        ),
    }, indent=2))


if __name__ == "__main__":
    main()
