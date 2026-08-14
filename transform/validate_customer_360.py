#!/usr/bin/env python3
"""Validate the deterministic Customer 360 semantic layer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


TESTS = [
    ("row_count_matches_customers",
     "SELECT COUNT(*) FROM customer_360",
     "SELECT COUNT(*) FROM stg_customers"),

    ("customer_id_unique",
     "SELECT COUNT(*) FROM customer_360",
     "SELECT COUNT(DISTINCT customer_id) FROM customer_360"),

    ("customer_id_not_null",
     "SELECT COUNT(*) FROM customer_360 WHERE customer_id IS NULL",
     "SELECT 0"),

    ("all_source_customers_present",
     """SELECT COUNT(*) FROM stg_customers c
        LEFT JOIN customer_360 x USING (customer_id)
        WHERE x.customer_id IS NULL""",
     "SELECT 0"),

    ("no_extra_customers",
     """SELECT COUNT(*) FROM customer_360 x
        LEFT JOIN stg_customers c USING (customer_id)
        WHERE c.customer_id IS NULL""",
     "SELECT 0"),

    ("first_seen_not_after_last_seen",
     "SELECT COUNT(*) FROM customer_360 WHERE first_seen_at > last_seen_at",
     "SELECT 0"),

    ("days_since_last_seen_nonnegative",
     "SELECT COUNT(*) FROM customer_360 WHERE days_since_last_seen < 0",
     "SELECT 0"),

    ("identity_count_positive",
     "SELECT COUNT(*) FROM customer_360 WHERE resolved_identity_count < 1",
     "SELECT 0"),

    ("lifetime_orders_ge_90d",
     "SELECT COUNT(*) FROM customer_360 WHERE lifetime_orders < orders_90d",
     "SELECT 0"),

    ("orders_90d_ge_60d",
     "SELECT COUNT(*) FROM customer_360 WHERE orders_90d < orders_60d",
     "SELECT 0"),

    ("orders_60d_ge_30d",
     "SELECT COUNT(*) FROM customer_360 WHERE orders_60d < orders_30d",
     "SELECT 0"),

    ("lifetime_value_nonnegative",
     "SELECT COUNT(*) FROM customer_360 WHERE lifetime_value < 0",
     "SELECT 0"),

    ("days_since_purchase_nonnegative",
     """SELECT COUNT(*) FROM customer_360
        WHERE days_since_purchase IS NOT NULL AND days_since_purchase < 0""",
     "SELECT 0"),

    ("refund_rate_bounded",
     """SELECT COUNT(*) FROM customer_360
        WHERE refund_rate_90d < 0 OR refund_rate_90d > 1""",
     "SELECT 0"),

    ("purchase_change_null_without_prior",
     """SELECT COUNT(*) FROM customer_360
        WHERE orders_prior_60d = 0 AND purchase_change_pct IS NOT NULL""",
     "SELECT 0"),

    ("purchase_decline_definition",
     """SELECT COUNT(*) FROM customer_360
        WHERE purchase_decline_flag !=
          (orders_prior_60d >= 2 AND orders_60d < orders_prior_60d)""",
     "SELECT 0"),

    ("sessions_90d_ge_60d",
     "SELECT COUNT(*) FROM customer_360 WHERE sessions_90d < sessions_60d",
     "SELECT 0"),

    ("sessions_60d_ge_30d",
     "SELECT COUNT(*) FROM customer_360 WHERE sessions_60d < sessions_30d",
     "SELECT 0"),

    ("engagement_change_null_without_prior",
     """SELECT COUNT(*) FROM customer_360
        WHERE sessions_prior_60d = 0 AND session_change_pct IS NOT NULL""",
     "SELECT 0"),

    ("engagement_decline_definition",
     """SELECT COUNT(*) FROM customer_360
        WHERE engagement_decline_flag !=
          (sessions_prior_60d >= 2 AND sessions_60d < sessions_prior_60d)""",
     "SELECT 0"),

    ("behavior_counts_nonnegative",
     """SELECT COUNT(*) FROM customer_360
        WHERE product_views_60d < 0
           OR add_to_cart_60d < 0
           OR checkout_starts_60d < 0""",
     "SELECT 0"),

    ("support_90d_le_lifetime",
     """SELECT COUNT(*) FROM customer_360
        WHERE support_cases_90d > support_cases_lifetime""",
     "SELECT 0"),

    ("open_support_le_lifetime",
     """SELECT COUNT(*) FROM customer_360
        WHERE open_support_cases > support_cases_lifetime""",
     "SELECT 0"),

    ("csat_bounded",
     """SELECT COUNT(*) FROM customer_360
        WHERE avg_csat_90d IS NOT NULL
          AND (avg_csat_90d < 1 OR avg_csat_90d > 5)""",
     "SELECT 0"),

    ("support_attention_definition",
     """SELECT COUNT(*) FROM customer_360
        WHERE support_attention_flag !=
          (open_support_cases > 0 OR negative_support_cases_90d >= 2)""",
     "SELECT 0"),

    ("email_open_rate_bounded",
     """SELECT COUNT(*) FROM customer_360
        WHERE email_open_rate_90d < 0 OR email_open_rate_90d > 1""",
     "SELECT 0"),

    ("email_click_rate_bounded",
     """SELECT COUNT(*) FROM customer_360
        WHERE email_click_rate_90d < 0 OR email_click_rate_90d > 1""",
     "SELECT 0"),

    ("email_opens_le_delivered",
     """SELECT COUNT(*) FROM customer_360
        WHERE email_opens_90d > email_delivered_90d""",
     "SELECT 0"),

    ("email_clicks_le_opens",
     """SELECT COUNT(*) FROM customer_360
        WHERE email_clicks_90d > email_opens_90d""",
     "SELECT 0"),

    ("active_subscriptions_nonnegative",
     """SELECT COUNT(*) FROM customer_360
        WHERE active_subscription_count < 0""",
     "SELECT 0"),

    ("preferred_category_requires_order",
     """SELECT COUNT(*) FROM customer_360
        WHERE lifetime_orders = 0 AND preferred_category IS NOT NULL""",
     "SELECT 0"),

    ("channel_affinity_requires_recent_session",
     """SELECT COUNT(*) FROM customer_360
        WHERE sessions_90d = 0 AND channel_affinity IS NOT NULL""",
     "SELECT 0"),

    ("single_as_of_timestamp",
     "SELECT COUNT(DISTINCT as_of_ts) FROM customer_360",
     "SELECT 1"),
]


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--database", type=Path, required=True)
    p.add_argument(
        "--report",
        type=Path,
        default=Path("data/warehouse/customer_360_validation.json"),
    )
    return p.parse_args()


def scalar(con, sql):
    return con.execute(sql).fetchone()[0]


def main():
    args = parse_args()

    try:
        import duckdb
    except ImportError as exc:
        raise SystemExit("Install DuckDB locally with: pip install duckdb") from exc

    con = duckdb.connect(str(args.database), read_only=True)
    results = []

    for name, actual_sql, expected_sql in TESTS:
        actual = scalar(con, actual_sql)
        expected = scalar(con, expected_sql)
        results.append({
            "name": name,
            "actual": actual,
            "expected": expected,
            "passed": actual == expected,
        })

    report = {
        "tests": len(results),
        "passed_tests": sum(r["passed"] for r in results),
        "failed_tests": sum(not r["passed"] for r in results),
        "passed": all(r["passed"] for r in results),
        "results": results,
    }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))

    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
