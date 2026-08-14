#!/usr/bin/env python3
"""Create 30 deterministic Commit 04 evaluation cases from customer_360.

These labels are an evaluation rubric, NOT a replacement churn model.
The hidden synthetic truth layer is intentionally not used.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


SEGMENTS = [
    {
        "case_type": "multiple_warning_signals",
        "where": """
            support_attention_flag
            AND (purchase_decline_flag OR engagement_decline_flag)
        """,
        "expected_risk_level": "HIGH",
        "required_evidence_any": [
            "support_attention_flag",
            "purchase_decline_flag",
            "engagement_decline_flag",
        ],
    },
    {
        "case_type": "purchase_decline_only",
        "where": """
            purchase_decline_flag
            AND NOT engagement_decline_flag
            AND NOT support_attention_flag
        """,
        "expected_risk_level": "MEDIUM",
        "required_evidence_any": ["purchase_decline_flag"],
    },
    {
        "case_type": "engagement_decline_only",
        "where": """
            engagement_decline_flag
            AND NOT purchase_decline_flag
            AND NOT support_attention_flag
        """,
        "expected_risk_level": "MEDIUM",
        "required_evidence_any": ["engagement_decline_flag"],
    },
    {
        "case_type": "support_attention_only",
        "where": """
            support_attention_flag
            AND NOT purchase_decline_flag
            AND NOT engagement_decline_flag
        """,
        "expected_risk_level": "MEDIUM",
        "required_evidence_any": ["support_attention_flag"],
    },
    {
        "case_type": "no_warning_signals",
        "where": """
            NOT purchase_decline_flag
            AND NOT engagement_decline_flag
            AND NOT support_attention_flag
            AND orders_60d > 0
            AND sessions_60d > 0
        """,
        "expected_risk_level": "LOW",
        "required_evidence_any": [],
    },
]


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--database", required=True)
    p.add_argument(
        "--output",
        type=Path,
        default=Path("evals/commit04/cases.jsonl"),
    )
    p.add_argument("--per-type", type=int, default=6)
    return p.parse_args()


def main():
    args = parse_args()
    import duckdb

    con = duckdb.connect(args.database, read_only=True)
    cases = []

    for spec in SEGMENTS:
        rows = con.execute(
            f"""
            SELECT customer_id
            FROM customer_360
            WHERE {spec["where"]}
            ORDER BY hash(customer_id)
            LIMIT ?
            """,
            [args.per_type],
        ).fetchall()

        if len(rows) < args.per_type:
            raise RuntimeError(
                f'Only {len(rows)} rows available for {spec["case_type"]}; '
                f'need {args.per_type}.'
            )

        for idx, (customer_id,) in enumerate(rows, start=1):
            cases.append({
                "case_id": f'{spec["case_type"]}_{idx:02d}',
                "case_type": spec["case_type"],
                "customer_id": customer_id,
                "expected_risk_level": spec["expected_risk_level"],
                "required_evidence_any": spec["required_evidence_any"],
            })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        for case in cases:
            f.write(json.dumps(case) + "\n")

    print(json.dumps({
        "cases": len(cases),
        "case_types": {
            spec["case_type"]: args.per_type for spec in SEGMENTS
        },
        "output": str(args.output),
        "note": (
            "Expected labels are a Commit 04 evaluation rubric over deterministic "
            "features, not a churn model."
        ),
    }, indent=2))


if __name__ == "__main__":
    main()
