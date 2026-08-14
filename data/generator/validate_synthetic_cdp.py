#!/usr/bin/env python3
"""
Validate a generated NovaCart synthetic CDP dataset.

The validator checks:
1. Required files exist.
2. Primary keys are unique where expected.
3. Foreign-key relationships are valid.
4. Order totals reconcile to order items.
5. Event duplication, lateness, anonymity, and profile-null rates are measurable.
6. Basic business-pattern distributions are reported.

It intentionally validates OBSERVED DATA, not hidden generator labels.
Generator-truth validation should be implemented separately so synthetic
labels do not leak into production-like CDP tables.

Example:
    python data/generator/validate_synthetic_cdp.py \
        --input-dir data/generated/dev \
        --report data/generated/dev/validation_report.json
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple


NOW_UTC = datetime(2026, 8, 13, 23, 0, 0, tzinfo=timezone.utc)

REQUIRED_FILES = [
    "customers.csv",
    "identities.csv",
    "products.csv",
    "orders.csv",
    "order_items.csv",
    "support_tickets.csv",
    "sessions.csv",
    "events.csv",
]

PRIMARY_KEYS = {
    "customers.csv": "customer_id",
    "identities.csv": "identity_id",
    "products.csv": "product_id",
    "orders.csv": "order_id",
    "order_items.csv": "order_item_id",
    "support_tickets.csv": "ticket_id",
    "sessions.csv": "session_id",
    # events.csv intentionally excluded: duplicate raw event IDs are expected.
}


def parse_args():
    parser = argparse.ArgumentParser(description="Validate NovaCart synthetic CDP data.")
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Optional JSON report path. Defaults to <input-dir>/validation_report.json",
    )
    parser.add_argument(
        "--reconciliation-tolerance",
        type=float,
        default=0.02,
        help="Allowed rounding difference when reconciling monetary values.",
    )
    return parser.parse_args()


def read_rows(path: Path) -> Iterable[dict]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        yield from csv.DictReader(handle)


def parse_dt(value: str) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def pct(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(100.0 * numerator / denominator, 3)


def collect_ids(path: Path, key: str) -> Tuple[Set[str], int, int]:
    ids: Set[str] = set()
    rows = 0
    duplicates = 0
    for row in read_rows(path):
        rows += 1
        value = row.get(key, "")
        if value in ids:
            duplicates += 1
        else:
            ids.add(value)
    return ids, rows, duplicates


def file_presence(input_dir: Path) -> dict:
    missing = [name for name in REQUIRED_FILES if not (input_dir / name).exists()]
    return {
        "passed": not missing,
        "missing_files": missing,
    }


def validate_primary_keys(input_dir: Path) -> Tuple[dict, Dict[str, Set[str]], Dict[str, int]]:
    result = {}
    id_sets: Dict[str, Set[str]] = {}
    row_counts: Dict[str, int] = {}

    for filename, pk in PRIMARY_KEYS.items():
        ids, rows, duplicates = collect_ids(input_dir / filename, pk)
        id_sets[filename] = ids
        row_counts[filename] = rows
        result[filename] = {
            "primary_key": pk,
            "rows": rows,
            "unique_ids": len(ids),
            "duplicate_primary_keys": duplicates,
            "passed": duplicates == 0 and "" not in ids,
        }

    # Event IDs are intentionally allowed to repeat in raw data.
    event_ids = []
    for row in read_rows(input_dir / "events.csv"):
        event_ids.append(row["event_id"])
    row_counts["events.csv"] = len(event_ids)
    result["events.csv"] = {
        "primary_key": "event_id",
        "rows": len(event_ids),
        "unique_ids": len(set(event_ids)),
        "duplicate_event_rows": len(event_ids) - len(set(event_ids)),
        "duplicate_event_rate_pct": pct(len(event_ids) - len(set(event_ids)), len(event_ids)),
        "passed": True,
        "note": "Duplicate raw event IDs are intentional.",
    }
    id_sets["events.csv"] = set(event_ids)

    return result, id_sets, row_counts


def validate_foreign_keys(input_dir: Path, ids: Dict[str, Set[str]]) -> dict:
    customer_ids = ids["customers.csv"]
    product_ids = ids["products.csv"]
    order_ids = ids["orders.csv"]
    session_ids = ids["sessions.csv"]
    identity_ids = ids["identities.csv"]

    checks = {}

    invalid_identity_customer = 0
    unresolved_identities = 0
    for row in read_rows(input_dir / "identities.csv"):
        customer_id = row["customer_id"]
        if not customer_id:
            unresolved_identities += 1
        elif customer_id not in customer_ids:
            invalid_identity_customer += 1
    checks["identities.customer_id"] = {
        "invalid_non_null_refs": invalid_identity_customer,
        "nullable_unresolved_rows": unresolved_identities,
        "passed": invalid_identity_customer == 0,
    }

    invalid_order_customer = sum(
        1
        for row in read_rows(input_dir / "orders.csv")
        if row["customer_id"] not in customer_ids
    )
    checks["orders.customer_id"] = {
        "invalid_refs": invalid_order_customer,
        "passed": invalid_order_customer == 0,
    }

    invalid_item_order = 0
    invalid_item_product = 0
    for row in read_rows(input_dir / "order_items.csv"):
        invalid_item_order += row["order_id"] not in order_ids
        invalid_item_product += row["product_id"] not in product_ids
    checks["order_items.order_id"] = {
        "invalid_refs": invalid_item_order,
        "passed": invalid_item_order == 0,
    }
    checks["order_items.product_id"] = {
        "invalid_refs": invalid_item_product,
        "passed": invalid_item_product == 0,
    }

    invalid_ticket_customer = 0
    invalid_ticket_order = 0
    for row in read_rows(input_dir / "support_tickets.csv"):
        invalid_ticket_customer += row["customer_id"] not in customer_ids
        if row["order_id"] and row["order_id"] not in order_ids:
            invalid_ticket_order += 1
    checks["support_tickets.customer_id"] = {
        "invalid_refs": invalid_ticket_customer,
        "passed": invalid_ticket_customer == 0,
    }
    checks["support_tickets.order_id"] = {
        "invalid_non_null_refs": invalid_ticket_order,
        "passed": invalid_ticket_order == 0,
    }

    invalid_session_customer = 0
    invalid_session_identity = 0
    anonymous_sessions = 0
    total_sessions = 0
    for row in read_rows(input_dir / "sessions.csv"):
        total_sessions += 1
        if not row["customer_id"]:
            anonymous_sessions += 1
        elif row["customer_id"] not in customer_ids:
            invalid_session_customer += 1
        if row["identity_id"] and row["identity_id"] not in identity_ids:
            invalid_session_identity += 1
    checks["sessions.customer_id"] = {
        "invalid_non_null_refs": invalid_session_customer,
        "anonymous_rows": anonymous_sessions,
        "anonymous_rate_pct": pct(anonymous_sessions, total_sessions),
        "passed": invalid_session_customer == 0,
    }
    checks["sessions.identity_id"] = {
        "invalid_non_null_refs": invalid_session_identity,
        "passed": invalid_session_identity == 0,
    }

    invalid_event_customer = 0
    invalid_event_identity = 0
    invalid_event_session = 0
    invalid_event_product = 0
    invalid_event_order = 0
    anonymous_events = 0
    total_events = 0
    for row in read_rows(input_dir / "events.csv"):
        total_events += 1
        if not row["customer_id"]:
            anonymous_events += 1
        elif row["customer_id"] not in customer_ids:
            invalid_event_customer += 1
        if row["identity_id"] and row["identity_id"] not in identity_ids:
            invalid_event_identity += 1
        if row["session_id"] and row["session_id"] not in session_ids:
            invalid_event_session += 1
        if row["product_id"] and row["product_id"] not in product_ids:
            invalid_event_product += 1
        if row["order_id"] and row["order_id"] not in order_ids:
            invalid_event_order += 1

    checks["events.customer_id"] = {
        "invalid_non_null_refs": invalid_event_customer,
        "anonymous_rows": anonymous_events,
        "anonymous_rate_pct": pct(anonymous_events, total_events),
        "passed": invalid_event_customer == 0,
    }
    checks["events.identity_id"] = {
        "invalid_non_null_refs": invalid_event_identity,
        "passed": invalid_event_identity == 0,
    }
    checks["events.session_id"] = {
        "invalid_non_null_refs": invalid_event_session,
        "passed": invalid_event_session == 0,
    }
    checks["events.product_id"] = {
        "invalid_non_null_refs": invalid_event_product,
        "passed": invalid_event_product == 0,
    }
    checks["events.order_id"] = {
        "invalid_non_null_refs": invalid_event_order,
        "passed": invalid_event_order == 0,
    }

    return checks


def validate_order_reconciliation(input_dir: Path, tolerance: float) -> dict:
    item_rollup = defaultdict(lambda: {"subtotal": 0.0, "discount": 0.0, "line_total": 0.0})
    for row in read_rows(input_dir / "order_items.csv"):
        qty = int(row["quantity"])
        unit_price = float(row["unit_price"])
        line_discount = float(row["line_discount"])
        line_total = float(row["line_total"])
        order_id = row["order_id"]
        item_rollup[order_id]["subtotal"] += qty * unit_price
        item_rollup[order_id]["discount"] += line_discount
        item_rollup[order_id]["line_total"] += line_total

    bad_subtotal = 0
    bad_discount = 0
    bad_total = 0
    missing_items = 0
    total_orders = 0
    examples = []

    for order in read_rows(input_dir / "orders.csv"):
        total_orders += 1
        order_id = order["order_id"]
        agg = item_rollup.get(order_id)
        if agg is None:
            missing_items += 1
            continue

        stored_subtotal = float(order["subtotal"])
        stored_discount = float(order["discount_amount"])
        tax = float(order["tax_amount"])
        shipping = float(order["shipping_amount"])
        stored_total = float(order["total_amount"])

        expected_subtotal = round(agg["subtotal"], 2)
        expected_discount = round(agg["discount"], 2)
        expected_total = round(expected_subtotal - expected_discount + tax + shipping, 2)

        subtotal_ok = abs(stored_subtotal - expected_subtotal) <= tolerance
        discount_ok = abs(stored_discount - expected_discount) <= tolerance
        total_ok = abs(stored_total - expected_total) <= tolerance

        bad_subtotal += not subtotal_ok
        bad_discount += not discount_ok
        bad_total += not total_ok

        if (not subtotal_ok or not discount_ok or not total_ok) and len(examples) < 5:
            examples.append({
                "order_id": order_id,
                "stored_subtotal": stored_subtotal,
                "expected_subtotal": expected_subtotal,
                "stored_discount": stored_discount,
                "expected_discount": expected_discount,
                "stored_total": stored_total,
                "expected_total": expected_total,
            })

    return {
        "orders_checked": total_orders,
        "orders_missing_items": missing_items,
        "subtotal_mismatches": int(bad_subtotal),
        "discount_mismatches": int(bad_discount),
        "total_mismatches": int(bad_total),
        "examples": examples,
        "passed": missing_items == 0 and bad_subtotal == 0 and bad_discount == 0 and bad_total == 0,
    }


def validate_event_quality(input_dir: Path) -> dict:
    total = 0
    late_over_1h = 0
    late_over_24h = 0
    negative_lag = 0
    event_type_counts = Counter()
    event_ids = Counter()

    for row in read_rows(input_dir / "events.csv"):
        total += 1
        event_ids[row["event_id"]] += 1
        event_type_counts[row["event_type"]] += 1

        event_time = parse_dt(row["event_timestamp"])
        received_at = parse_dt(row["received_at"])
        if event_time and received_at:
            lag = received_at - event_time
            if lag.total_seconds() < 0:
                negative_lag += 1
            if lag > timedelta(hours=1):
                late_over_1h += 1
            if lag > timedelta(hours=24):
                late_over_24h += 1

    duplicate_rows = sum(count - 1 for count in event_ids.values() if count > 1)

    return {
        "total_raw_event_rows": total,
        "unique_event_ids": len(event_ids),
        "duplicate_event_rows": duplicate_rows,
        "duplicate_event_rate_pct": pct(duplicate_rows, total),
        "late_over_1h_rows": late_over_1h,
        "late_over_1h_rate_pct": pct(late_over_1h, total),
        "late_over_24h_rows": late_over_24h,
        "late_over_24h_rate_pct": pct(late_over_24h, total),
        "negative_ingestion_lag_rows": negative_lag,
        "event_type_distribution": dict(event_type_counts.most_common()),
        "passed": negative_lag == 0,
    }


def profile_nulls(input_dir: Path) -> dict:
    fields = ["phone", "state", "city", "postal_code", "date_of_birth"]
    null_counts = Counter()
    total = 0

    for row in read_rows(input_dir / "customers.csv"):
        total += 1
        for field in fields:
            if not row[field]:
                null_counts[field] += 1

    by_field = {
        field: {
            "null_rows": null_counts[field],
            "null_rate_pct": pct(null_counts[field], total),
        }
        for field in fields
    }
    total_cells = total * len(fields)
    total_nulls = sum(null_counts.values())

    return {
        "customers": total,
        "fields_profiled": fields,
        "by_field": by_field,
        "overall_profile_null_rate_pct": pct(total_nulls, total_cells),
    }


def observed_business_patterns(input_dir: Path) -> dict:
    """
    Report useful observed patterns without depending on hidden generator labels.
    These are diagnostics, not ground-truth segment validation.
    """
    recent_start = NOW_UTC - timedelta(days=60)
    prior_start = NOW_UTC - timedelta(days=120)

    customer_order_periods = defaultdict(lambda: {"recent": 0, "prior": 0})
    discounted_orders = 0
    total_orders = 0
    total_discount = 0.0

    for row in read_rows(input_dir / "orders.csv"):
        total_orders += 1
        customer_id = row["customer_id"]
        ts = parse_dt(row["order_timestamp"])
        discount = float(row["discount_amount"])
        total_discount += discount
        if discount > 0:
            discounted_orders += 1

        if ts:
            if recent_start <= ts <= NOW_UTC:
                customer_order_periods[customer_id]["recent"] += 1
            elif prior_start <= ts < recent_start:
                customer_order_periods[customer_id]["prior"] += 1

    comparable = 0
    declining = 0
    stable_or_growing = 0
    for periods in customer_order_periods.values():
        if periods["recent"] or periods["prior"]:
            comparable += 1
            if periods["recent"] < periods["prior"]:
                declining += 1
            else:
                stable_or_growing += 1

    recent_tickets = 0
    unresolved_recent_tickets = 0
    negative_recent_tickets = 0
    ticket_customers = set()

    for row in read_rows(input_dir / "support_tickets.csv"):
        opened = parse_dt(row["opened_at"])
        if opened and opened >= recent_start:
            recent_tickets += 1
            ticket_customers.add(row["customer_id"])
            if row["status"] in {"OPEN", "PENDING"}:
                unresolved_recent_tickets += 1
            if row["sentiment"] == "NEGATIVE":
                negative_recent_tickets += 1

    return {
        "purchase_behavior_last_120d": {
            "customers_with_recent_or_prior_orders": comparable,
            "customers_with_fewer_orders_in_recent_60d_than_prior_60d": declining,
            "observed_declining_rate_pct": pct(declining, comparable),
            "customers_stable_or_growing": stable_or_growing,
        },
        "discount_behavior": {
            "total_orders": total_orders,
            "discounted_orders": discounted_orders,
            "discounted_order_rate_pct": pct(discounted_orders, total_orders),
            "total_discount_amount": round(total_discount, 2),
        },
        "support_behavior_last_60d": {
            "recent_tickets": recent_tickets,
            "customers_with_recent_tickets": len(ticket_customers),
            "unresolved_recent_tickets": unresolved_recent_tickets,
            "unresolved_recent_ticket_rate_pct": pct(unresolved_recent_tickets, recent_tickets),
            "negative_recent_tickets": negative_recent_tickets,
            "negative_recent_ticket_rate_pct": pct(negative_recent_tickets, recent_tickets),
        },
        "note": (
            "These are observed data distributions. They do not prove hidden generator "
            "segments behaved as intended because generator truth is not stored in CDP tables."
        ),
    }


def overall_status(report: dict) -> bool:
    sections = [
        report["file_presence"]["passed"],
        all(v["passed"] for v in report["primary_keys"].values()),
        all(v["passed"] for v in report["foreign_keys"].values()),
        report["order_reconciliation"]["passed"],
        report["event_quality"]["passed"],
    ]
    return all(sections)


def main():
    args = parse_args()
    input_dir = args.input_dir
    report_path = args.report or (input_dir / "validation_report.json")

    presence = file_presence(input_dir)
    if not presence["passed"]:
        report = {
            "passed": False,
            "file_presence": presence,
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        raise SystemExit(1)

    pk_results, ids, row_counts = validate_primary_keys(input_dir)

    report = {
        "dataset_path": str(input_dir),
        "validated_at": NOW_UTC.isoformat(),
        "file_presence": presence,
        "row_counts": row_counts,
        "primary_keys": pk_results,
        "foreign_keys": validate_foreign_keys(input_dir, ids),
        "order_reconciliation": validate_order_reconciliation(
            input_dir, args.reconciliation_tolerance
        ),
        "event_quality": validate_event_quality(input_dir),
        "profile_nulls": profile_nulls(input_dir),
        "observed_business_patterns": observed_business_patterns(input_dir),
    }
    report["passed"] = overall_status(report)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
