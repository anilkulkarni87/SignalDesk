#!/usr/bin/env python3
"""
Validate semantic realism of the NovaCart synthetic CDP.

This validator uses generator truth labels from:
    <input-dir>/_truth/customer_generation_truth.csv

and compares them to OBSERVED behavior in:
    sessions.csv
    orders.csv
    support_tickets.csv

The truth file is test-only. SignalDesk application code should never read it.

Example:
    python data/generator/validate_semantic_behavior.py \
        --input-dir data/generated/dev \
        --report data/generated/dev/semantic_validation_report.json
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median
from typing import Dict, Iterable, Optional


NOW_UTC = datetime(2026, 8, 13, 23, 0, 0, tzinfo=timezone.utc)
RECENT_START = NOW_UTC - timedelta(days=60)
PRIOR_START = NOW_UTC - timedelta(days=120)


def parse_args():
    parser = argparse.ArgumentParser(description="Validate NovaCart semantic behavior.")
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Defaults to <input-dir>/semantic_validation_report.json",
    )
    parser.add_argument(
        "--decline-pass-rate",
        type=float,
        default=0.75,
        help="Minimum share of declining customers that should show lower recent activity.",
    )
    parser.add_argument(
        "--support-lift-ratio",
        type=float,
        default=2.0,
        help="Minimum support ticket-rate lift vs stable customers.",
    )
    parser.add_argument(
        "--discount-lift-points",
        type=float,
        default=20.0,
        help="Minimum discounted-order percentage-point lift vs stable customers.",
    )
    parser.add_argument(
        "--dormant-recent-session-max",
        type=float,
        default=1.0,
        help="Maximum mean recent sessions for dormant customers.",
    )
    return parser.parse_args()


def resolve_table_path(path: Path) -> Path:
    if path.exists():
        return path
    parquet = path.with_suffix(".parquet")
    if parquet.exists():
        return parquet
    csv_path = path.with_suffix(".csv")
    if csv_path.exists():
        return csv_path
    raise FileNotFoundError(path)


def read_rows(path: Path) -> Iterable[dict]:
    resolved = resolve_table_path(path)

    if resolved.suffix == ".csv":
        with resolved.open(
            "r",
            newline="",
            encoding="utf-8",
            buffering=4 * 1024 * 1024,
        ) as f:
            yield from csv.DictReader(f)
        return

    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError(
            "Reading Parquet semantic-validation input requires pyarrow."
        ) from exc

    parquet_file = pq.ParquetFile(resolved)
    for batch in parquet_file.iter_batches(batch_size=65_536):
        for row in batch.to_pylist():
            yield {k: ("" if v is None else v) for k, v in row.items()}


def parse_dt(value: str) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def pct(n: float, d: float) -> float:
    return 0.0 if not d else round(100.0 * n / d, 3)


def safe_ratio(n: float, d: float) -> Optional[float]:
    if d == 0:
        return None
    return round(n / d, 3)


def load_truth(input_dir: Path) -> Dict[str, str]:
    path = input_dir / "_truth" / "customer_generation_truth.csv"
    resolved = resolve_table_path(path)
    return {
        row["customer_id"]: row["synthetic_segment"]
        for row in read_rows(resolved)
    }


def build_features(input_dir: Path, truth: Dict[str, str]) -> Dict[str, dict]:
    features = {
        customer_id: {
            "segment": segment,
            "recent_sessions": 0,
            "prior_sessions": 0,
            "recent_orders": 0,
            "prior_orders": 0,
            "total_orders": 0,
            "discounted_orders": 0,
            "recent_tickets": 0,
            "recent_unresolved_tickets": 0,
            "recent_negative_tickets": 0,
        }
        for customer_id, segment in truth.items()
    }

    for row in read_rows(input_dir / "sessions.csv"):
        customer_id = row["customer_id"]
        if not customer_id or customer_id not in features:
            continue
        ts = parse_dt(row["session_started_at"])
        if not ts:
            continue
        if RECENT_START <= ts <= NOW_UTC:
            features[customer_id]["recent_sessions"] += 1
        elif PRIOR_START <= ts < RECENT_START:
            features[customer_id]["prior_sessions"] += 1

    for row in read_rows(input_dir / "orders.csv"):
        customer_id = row["customer_id"]
        if customer_id not in features:
            continue
        ts = parse_dt(row["order_timestamp"])
        features[customer_id]["total_orders"] += 1
        if float(row["discount_amount"]) > 0:
            features[customer_id]["discounted_orders"] += 1
        if ts:
            if RECENT_START <= ts <= NOW_UTC:
                features[customer_id]["recent_orders"] += 1
            elif PRIOR_START <= ts < RECENT_START:
                features[customer_id]["prior_orders"] += 1

    for row in read_rows(input_dir / "support_tickets.csv"):
        customer_id = row["customer_id"]
        if customer_id not in features:
            continue
        opened = parse_dt(row["opened_at"])
        if not opened or opened < RECENT_START:
            continue
        features[customer_id]["recent_tickets"] += 1
        if row["status"] in {"OPEN", "PENDING"}:
            features[customer_id]["recent_unresolved_tickets"] += 1
        if row["sentiment"] == "NEGATIVE":
            features[customer_id]["recent_negative_tickets"] += 1

    return features


def rows_for_segment(features: Dict[str, dict], segment: str):
    return [v for v in features.values() if v["segment"] == segment]


def summarize_segment(rows):
    n = len(rows)
    total_orders = sum(r["total_orders"] for r in rows)
    discounted_orders = sum(r["discounted_orders"] for r in rows)
    recent_tickets = sum(r["recent_tickets"] for r in rows)
    unresolved = sum(r["recent_unresolved_tickets"] for r in rows)
    negative = sum(r["recent_negative_tickets"] for r in rows)

    recent_sessions_values = [r["recent_sessions"] for r in rows]
    prior_sessions_values = [r["prior_sessions"] for r in rows]
    recent_orders_values = [r["recent_orders"] for r in rows]
    prior_orders_values = [r["prior_orders"] for r in rows]

    return {
        "customers": n,
        "mean_recent_sessions": round(mean(recent_sessions_values), 3) if rows else 0.0,
        "mean_prior_sessions": round(mean(prior_sessions_values), 3) if rows else 0.0,
        "median_recent_sessions": median(recent_sessions_values) if rows else 0,
        "mean_recent_orders": round(mean(recent_orders_values), 3) if rows else 0.0,
        "mean_prior_orders": round(mean(prior_orders_values), 3) if rows else 0.0,
        "discounted_order_rate_pct": pct(discounted_orders, total_orders),
        "recent_ticket_rate_per_customer": round(recent_tickets / n, 3) if n else 0.0,
        "unresolved_recent_ticket_rate_pct": pct(unresolved, recent_tickets),
        "negative_recent_ticket_rate_pct": pct(negative, recent_tickets),
    }


def validate_declining(features: Dict[str, dict], min_pass_rate: float) -> dict:
    rows = rows_for_segment(features, "declining_engagement")
    if not rows:
        return {"passed": False, "reason": "No declining_engagement customers generated."}

    passing = 0
    session_declines = 0
    order_declines = 0
    comparable = 0

    for r in rows:
        session_decline = r["recent_sessions"] < r["prior_sessions"]
        order_decline = r["recent_orders"] < r["prior_orders"]

        if session_decline:
            session_declines += 1
        if order_decline:
            order_declines += 1

        # Only count cases where either period has observable activity.
        if (
            r["recent_sessions"] or r["prior_sessions"] or
            r["recent_orders"] or r["prior_orders"]
        ):
            comparable += 1
            if session_decline or order_decline:
                passing += 1

    pass_rate = 0.0 if comparable == 0 else passing / comparable

    return {
        "customers": len(rows),
        "comparable_customers": comparable,
        "customers_showing_decline": passing,
        "decline_pass_rate_pct": round(pass_rate * 100, 3),
        "session_decline_rate_pct": pct(session_declines, len(rows)),
        "order_decline_rate_pct": pct(order_declines, len(rows)),
        "target_pct": round(min_pass_rate * 100, 1),
        "passed": pass_rate >= min_pass_rate,
    }


def validate_support(features: Dict[str, dict], min_lift_ratio: float) -> dict:
    support_rows = rows_for_segment(features, "support_issue")
    stable_rows = rows_for_segment(features, "stable")

    if not support_rows or not stable_rows:
        return {"passed": False, "reason": "Missing support_issue or stable customers."}

    support_summary = summarize_segment(support_rows)
    stable_summary = summarize_segment(stable_rows)

    support_rate = support_summary["recent_ticket_rate_per_customer"]
    stable_rate = stable_summary["recent_ticket_rate_per_customer"]

    lift = None if stable_rate == 0 else support_rate / stable_rate
    negative_ok = (
        support_summary["negative_recent_ticket_rate_pct"]
        > stable_summary["negative_recent_ticket_rate_pct"]
    )
    unresolved_ok = (
        support_summary["unresolved_recent_ticket_rate_pct"]
        > stable_summary["unresolved_recent_ticket_rate_pct"]
    )

    return {
        "support_issue_recent_ticket_rate_per_customer": support_rate,
        "stable_recent_ticket_rate_per_customer": stable_rate,
        "ticket_rate_lift_ratio": None if lift is None else round(lift, 3),
        "minimum_ticket_rate_lift_ratio": min_lift_ratio,
        "support_issue_negative_ticket_rate_pct": support_summary["negative_recent_ticket_rate_pct"],
        "stable_negative_ticket_rate_pct": stable_summary["negative_recent_ticket_rate_pct"],
        "support_issue_unresolved_ticket_rate_pct": support_summary["unresolved_recent_ticket_rate_pct"],
        "stable_unresolved_ticket_rate_pct": stable_summary["unresolved_recent_ticket_rate_pct"],
        "passed": (
            lift is not None
            and lift >= min_lift_ratio
            and negative_ok
            and unresolved_ok
        ),
    }


def validate_price_sensitive(features: Dict[str, dict], min_lift_points: float) -> dict:
    price_rows = rows_for_segment(features, "price_sensitive")
    stable_rows = rows_for_segment(features, "stable")

    if not price_rows or not stable_rows:
        return {"passed": False, "reason": "Missing price_sensitive or stable customers."}

    price_summary = summarize_segment(price_rows)
    stable_summary = summarize_segment(stable_rows)

    lift_points = (
        price_summary["discounted_order_rate_pct"]
        - stable_summary["discounted_order_rate_pct"]
    )

    return {
        "price_sensitive_discounted_order_rate_pct": price_summary["discounted_order_rate_pct"],
        "stable_discounted_order_rate_pct": stable_summary["discounted_order_rate_pct"],
        "lift_percentage_points": round(lift_points, 3),
        "minimum_lift_percentage_points": min_lift_points,
        "passed": lift_points >= min_lift_points,
    }


def validate_dormant(features: Dict[str, dict], max_mean_recent_sessions: float) -> dict:
    dormant_rows = rows_for_segment(features, "dormant")
    stable_rows = rows_for_segment(features, "stable")

    if not dormant_rows or not stable_rows:
        return {"passed": False, "reason": "Missing dormant or stable customers."}

    dormant_summary = summarize_segment(dormant_rows)
    stable_summary = summarize_segment(stable_rows)

    session_ok = dormant_summary["mean_recent_sessions"] <= max_mean_recent_sessions
    order_ok = dormant_summary["mean_recent_orders"] < stable_summary["mean_recent_orders"]

    return {
        "dormant_mean_recent_sessions": dormant_summary["mean_recent_sessions"],
        "stable_mean_recent_sessions": stable_summary["mean_recent_sessions"],
        "maximum_dormant_mean_recent_sessions": max_mean_recent_sessions,
        "dormant_mean_recent_orders": dormant_summary["mean_recent_orders"],
        "stable_mean_recent_orders": stable_summary["mean_recent_orders"],
        "passed": session_ok and order_ok,
    }


def main():
    args = parse_args()
    report_path = args.report or (args.input_dir / "semantic_validation_report.json")

    truth = load_truth(args.input_dir)
    features = build_features(args.input_dir, truth)

    segments = sorted(set(truth.values()))
    segment_summaries = {
        segment: summarize_segment(rows_for_segment(features, segment))
        for segment in segments
    }

    tests = {
        "declining_engagement": validate_declining(features, args.decline_pass_rate),
        "support_issue": validate_support(features, args.support_lift_ratio),
        "price_sensitive": validate_price_sensitive(features, args.discount_lift_points),
        "dormant": validate_dormant(features, args.dormant_recent_session_max),
    }

    passed = all(test.get("passed", False) for test in tests.values())

    report = {
        "validated_at": NOW_UTC.isoformat(),
        "input_dir": str(args.input_dir),
        "truth_customers": len(truth),
        "segment_summaries": segment_summaries,
        "tests": tests,
        "passed": passed,
        "interpretation": (
            "PASS means the generated population shows the intended segment-level "
            "directional behavior at the configured thresholds. It does not imply "
            "real-world causal validity."
        ),
    }

    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
