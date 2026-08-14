#!/usr/bin/env python3
"""
Scale-oriented structural validator for NovaCart synthetic CDP CSV output.

Design:
- One streaming pass per large file.
- O(1) primary-key uniqueness checks by verifying generator IDs are strictly
  increasing (events are non-decreasing because raw duplicates are intentional).
- Foreign-key validation uses generated ID ranges from manifest row counts.
- Order/order-item reconciliation is a streaming merge, not a large dictionary.

This validator is intentionally specific to the NovaCart synthetic generator's
sequential ID contract. It is not a generic CSV database validator.

Example:
    python data/generator/validate_synthetic_cdp_fast.py \
        --input-dir data/generated/full
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple


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
    "manifest.json",
]

ID_CONTRACTS = {
    "customer_id": ("C", 7, "customers"),
    "identity_id": ("I", 9, "identities"),
    "product_id": ("P", 6, "products"),
    "order_id": ("O", 9, "orders"),
    "order_item_id": ("OI", 10, "order_items"),
    "ticket_id": ("T", 8, "support_tickets"),
    "session_id": ("S", 10, "sessions"),
    "event_id": ("E", 12, None),
}


def parse_args():
    parser = argparse.ArgumentParser(description="Fast structural validation for NovaCart synthetic data.")
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--reconciliation-tolerance", type=float, default=0.02)
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
            "Reading Parquet validation input requires pyarrow."
        ) from exc

    parquet_file = pq.ParquetFile(resolved)
    for batch in parquet_file.iter_batches(batch_size=65_536):
        for row in batch.to_pylist():
            # Preserve CSV-style missing-value semantics used by validators.
            yield {k: ("" if v is None else v) for k, v in row.items()}


def parse_dt(value: str) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def pct(n: float, d: float) -> float:
    return 0.0 if not d else round(100.0 * n / d, 3)


def parse_generated_id(value: str, prefix: str, width: int) -> Optional[int]:
    if not value or not value.startswith(prefix):
        return None
    suffix = value[len(prefix):]
    if len(suffix) != width or not suffix.isdigit():
        return None
    return int(suffix)


def valid_ref(value: str, field: str, max_value: int, nullable: bool = False) -> bool:
    if not value:
        return nullable
    prefix, width, _ = ID_CONTRACTS[field]
    number = parse_generated_id(value, prefix, width)
    return number is not None and 1 <= number <= max_value


def check_monotonic_pk(
    path: Path,
    pk: str,
    allow_equal: bool = False,
) -> Tuple[int, int, int, int]:
    """
    Returns: rows, malformed, duplicate_equal, out_of_order.
    Strictly increasing implies uniqueness for generator IDs.
    """
    prefix, width, _ = ID_CONTRACTS[pk]
    previous = 0
    rows = malformed = duplicate_equal = out_of_order = 0

    for row in read_rows(path):
        rows += 1
        current = parse_generated_id(row.get(pk, ""), prefix, width)
        if current is None:
            malformed += 1
            continue
        if current == previous:
            duplicate_equal += 1
            if not allow_equal:
                out_of_order += 1
        elif current < previous:
            out_of_order += 1
        previous = current

    return rows, malformed, duplicate_equal, out_of_order


def validate_customer_profiles(input_dir: Path, expected_rows: int) -> Tuple[dict, dict]:
    fields = ["phone", "state", "city", "postal_code", "date_of_birth"]
    null_counts = {field: 0 for field in fields}
    rows = 0
    malformed_refs = 0
    previous = 0

    for row in read_rows(input_dir / "customers.csv"):
        rows += 1
        current = parse_generated_id(row["customer_id"], "C", 7)
        if current is None or current <= previous:
            malformed_refs += 1
        if current is not None:
            previous = current

        for field in fields:
            if not row[field]:
                null_counts[field] += 1

    total_cells = rows * len(fields)
    total_nulls = sum(null_counts.values())

    pk = {
        "rows": rows,
        "expected_rows": expected_rows,
        "malformed_or_non_monotonic": malformed_refs,
        "passed": rows == expected_rows and malformed_refs == 0,
    }
    profile = {
        "customers": rows,
        "fields_profiled": fields,
        "by_field": {
            field: {
                "null_rows": null_counts[field],
                "null_rate_pct": pct(null_counts[field], rows),
            }
            for field in fields
        },
        "overall_profile_null_rate_pct": pct(total_nulls, total_cells),
    }
    return pk, profile


def validate_identities(input_dir: Path, counts: Dict[str, int]) -> Tuple[dict, dict]:
    rows = invalid_pk = invalid_customer = unresolved = 0
    previous = 0

    for row in read_rows(input_dir / "identities.csv"):
        rows += 1
        current = parse_generated_id(row["identity_id"], "I", 9)
        if current is None or current <= previous:
            invalid_pk += 1
        if current is not None:
            previous = current

        customer_id = row["customer_id"]
        if not customer_id:
            unresolved += 1
        elif not valid_ref(customer_id, "customer_id", counts["customers"]):
            invalid_customer += 1

    return (
        {
            "rows": rows,
            "expected_rows": counts["identities"],
            "malformed_or_non_monotonic": invalid_pk,
            "passed": rows == counts["identities"] and invalid_pk == 0,
        },
        {
            "invalid_non_null_refs": invalid_customer,
            "nullable_unresolved_rows": unresolved,
            "passed": invalid_customer == 0,
        },
    )


def validate_simple_pk(path: Path, pk: str, expected_rows: int) -> dict:
    rows, malformed, duplicates, out_of_order = check_monotonic_pk(path, pk)
    return {
        "rows": rows,
        "expected_rows": expected_rows,
        "malformed_ids": malformed,
        "duplicate_or_out_of_order": out_of_order,
        "passed": rows == expected_rows and malformed == 0 and out_of_order == 0,
    }


def reconcile_orders(input_dir: Path, counts: Dict[str, int], tolerance: float) -> Tuple[dict, dict, dict]:
    """
    Stream orders and order_items together. Both files are grouped by ascending order_id.
    """
    item_iter = iter(read_rows(input_dir / "order_items.csv"))
    current_item = next(item_iter, None)

    orders = 0
    invalid_order_pk = 0
    invalid_order_customer = 0
    previous_order_num = 0

    missing_items = 0
    subtotal_mismatches = 0
    discount_mismatches = 0
    total_mismatches = 0

    item_rows = 0
    invalid_item_pk = 0
    invalid_item_order = 0
    invalid_item_product = 0
    previous_item_num = 0
    examples = []

    def consume_item(item: dict):
        nonlocal item_rows, invalid_item_pk, invalid_item_order, invalid_item_product, previous_item_num
        item_rows += 1
        item_num = parse_generated_id(item["order_item_id"], "OI", 10)
        if item_num is None or item_num <= previous_item_num:
            invalid_item_pk += 1
        if item_num is not None:
            previous_item_num = item_num

        if not valid_ref(item["order_id"], "order_id", counts["orders"]):
            invalid_item_order += 1
        if not valid_ref(item["product_id"], "product_id", counts["products"]):
            invalid_item_product += 1

    for order in read_rows(input_dir / "orders.csv"):
        orders += 1
        order_num = parse_generated_id(order["order_id"], "O", 9)
        if order_num is None or order_num <= previous_order_num:
            invalid_order_pk += 1
        if order_num is not None:
            previous_order_num = order_num

        if not valid_ref(order["customer_id"], "customer_id", counts["customers"]):
            invalid_order_customer += 1

        target_order_id = order["order_id"]
        subtotal = discount = line_total = 0.0
        matched_items = 0

        while current_item is not None and current_item["order_id"] < target_order_id:
            consume_item(current_item)
            current_item = next(item_iter, None)

        while current_item is not None and current_item["order_id"] == target_order_id:
            consume_item(current_item)
            qty = int(current_item["quantity"])
            unit_price = float(current_item["unit_price"])
            line_discount = float(current_item["line_discount"])
            item_line_total = float(current_item["line_total"])

            subtotal += qty * unit_price
            discount += line_discount
            line_total += item_line_total
            matched_items += 1
            current_item = next(item_iter, None)

        if matched_items == 0:
            missing_items += 1
            continue

        expected_subtotal = round(subtotal, 2)
        expected_discount = round(discount, 2)
        expected_total = round(
            expected_subtotal
            - expected_discount
            + float(order["tax_amount"])
            + float(order["shipping_amount"]),
            2,
        )

        stored_subtotal = float(order["subtotal"])
        stored_discount = float(order["discount_amount"])
        stored_total = float(order["total_amount"])

        subtotal_ok = abs(stored_subtotal - expected_subtotal) <= tolerance
        discount_ok = abs(stored_discount - expected_discount) <= tolerance
        total_ok = abs(stored_total - expected_total) <= tolerance

        subtotal_mismatches += not subtotal_ok
        discount_mismatches += not discount_ok
        total_mismatches += not total_ok

        if (not subtotal_ok or not discount_ok or not total_ok) and len(examples) < 5:
            examples.append({
                "order_id": target_order_id,
                "stored_total": stored_total,
                "expected_total": expected_total,
            })

    while current_item is not None:
        consume_item(current_item)
        current_item = next(item_iter, None)

    order_pk = {
        "rows": orders,
        "expected_rows": counts["orders"],
        "malformed_or_non_monotonic": invalid_order_pk,
        "passed": orders == counts["orders"] and invalid_order_pk == 0,
    }
    item_pk = {
        "rows": item_rows,
        "expected_rows": counts["order_items"],
        "malformed_or_non_monotonic": invalid_item_pk,
        "passed": item_rows == counts["order_items"] and invalid_item_pk == 0,
    }

    checks = {
        "orders.customer_id": {
            "invalid_refs": invalid_order_customer,
            "passed": invalid_order_customer == 0,
        },
        "order_items.order_id": {
            "invalid_refs": invalid_item_order,
            "passed": invalid_item_order == 0,
        },
        "order_items.product_id": {
            "invalid_refs": invalid_item_product,
            "passed": invalid_item_product == 0,
        },
    }

    reconciliation = {
        "orders_checked": orders,
        "orders_missing_items": missing_items,
        "subtotal_mismatches": int(subtotal_mismatches),
        "discount_mismatches": int(discount_mismatches),
        "total_mismatches": int(total_mismatches),
        "examples": examples,
        "passed": (
            missing_items == 0
            and subtotal_mismatches == 0
            and discount_mismatches == 0
            and total_mismatches == 0
        ),
    }

    return {"orders.csv": order_pk, "order_items.csv": item_pk}, checks, reconciliation


def validate_support(input_dir: Path, counts: Dict[str, int]) -> Tuple[dict, dict]:
    rows = invalid_pk = invalid_customer = invalid_order = 0
    previous = 0

    for row in read_rows(input_dir / "support_tickets.csv"):
        rows += 1
        current = parse_generated_id(row["ticket_id"], "T", 8)
        if current is None or current <= previous:
            invalid_pk += 1
        if current is not None:
            previous = current

        if not valid_ref(row["customer_id"], "customer_id", counts["customers"]):
            invalid_customer += 1
        if row["order_id"] and not valid_ref(row["order_id"], "order_id", counts["orders"]):
            invalid_order += 1

    return (
        {
            "rows": rows,
            "expected_rows": counts["support_tickets"],
            "malformed_or_non_monotonic": invalid_pk,
            "passed": rows == counts["support_tickets"] and invalid_pk == 0,
        },
        {
            "support_tickets.customer_id": {
                "invalid_refs": invalid_customer,
                "passed": invalid_customer == 0,
            },
            "support_tickets.order_id": {
                "invalid_non_null_refs": invalid_order,
                "passed": invalid_order == 0,
            },
        },
    )


def validate_sessions(input_dir: Path, counts: Dict[str, int]) -> Tuple[dict, dict]:
    rows = invalid_pk = invalid_customer = invalid_identity = anonymous = 0
    previous = 0

    for row in read_rows(input_dir / "sessions.csv"):
        rows += 1
        current = parse_generated_id(row["session_id"], "S", 10)
        if current is None or current <= previous:
            invalid_pk += 1
        if current is not None:
            previous = current

        if not row["customer_id"]:
            anonymous += 1
        elif not valid_ref(row["customer_id"], "customer_id", counts["customers"]):
            invalid_customer += 1

        if row["identity_id"] and not valid_ref(
            row["identity_id"], "identity_id", counts["identities"]
        ):
            invalid_identity += 1

    return (
        {
            "rows": rows,
            "expected_rows": counts["sessions"],
            "malformed_or_non_monotonic": invalid_pk,
            "passed": rows == counts["sessions"] and invalid_pk == 0,
        },
        {
            "sessions.customer_id": {
                "invalid_non_null_refs": invalid_customer,
                "anonymous_rows": anonymous,
                "anonymous_rate_pct": pct(anonymous, rows),
                "passed": invalid_customer == 0,
            },
            "sessions.identity_id": {
                "invalid_non_null_refs": invalid_identity,
                "passed": invalid_identity == 0,
            },
        },
    )


def validate_events(input_dir: Path, counts: Dict[str, int]) -> Tuple[dict, dict, dict]:
    rows = malformed_id = out_of_order = duplicates = 0
    previous_event_num = 0

    invalid_customer = invalid_identity = invalid_session = invalid_product = invalid_order = 0
    anonymous = 0
    late_1h = late_24h = negative_lag = 0
    event_types: Dict[str, int] = {}

    for row in read_rows(input_dir / "events.csv"):
        rows += 1
        event_num = parse_generated_id(row["event_id"], "E", 12)
        if event_num is None:
            malformed_id += 1
        else:
            if event_num == previous_event_num:
                duplicates += 1
            elif event_num < previous_event_num:
                out_of_order += 1
            previous_event_num = event_num

        customer_id = row["customer_id"]
        if not customer_id:
            anonymous += 1
        elif not valid_ref(customer_id, "customer_id", counts["customers"]):
            invalid_customer += 1

        if row["identity_id"] and not valid_ref(
            row["identity_id"], "identity_id", counts["identities"]
        ):
            invalid_identity += 1
        if row["session_id"] and not valid_ref(
            row["session_id"], "session_id", counts["sessions"]
        ):
            invalid_session += 1
        if row["product_id"] and not valid_ref(
            row["product_id"], "product_id", counts["products"]
        ):
            invalid_product += 1
        if row["order_id"] and not valid_ref(
            row["order_id"], "order_id", counts["orders"]
        ):
            invalid_order += 1

        event_type = row["event_type"]
        event_types[event_type] = event_types.get(event_type, 0) + 1

        event_time = parse_dt(row["event_timestamp"])
        received = parse_dt(row["received_at"])
        if event_time and received:
            lag = received - event_time
            if lag.total_seconds() < 0:
                negative_lag += 1
            if lag > timedelta(hours=1):
                late_1h += 1
            if lag > timedelta(hours=24):
                late_24h += 1

    pk = {
        "rows": rows,
        "expected_rows": counts["events_raw_rows"],
        "malformed_ids": malformed_id,
        "out_of_order_ids": out_of_order,
        "duplicate_event_rows": duplicates,
        "duplicate_event_rate_pct": pct(duplicates, rows),
        "passed": (
            rows == counts["events_raw_rows"]
            and malformed_id == 0
            and out_of_order == 0
        ),
        "note": "Equal adjacent event IDs are intentional raw duplicates.",
    }

    fk = {
        "events.customer_id": {
            "invalid_non_null_refs": invalid_customer,
            "anonymous_rows": anonymous,
            "anonymous_rate_pct": pct(anonymous, rows),
            "passed": invalid_customer == 0,
        },
        "events.identity_id": {
            "invalid_non_null_refs": invalid_identity,
            "passed": invalid_identity == 0,
        },
        "events.session_id": {
            "invalid_non_null_refs": invalid_session,
            "passed": invalid_session == 0,
        },
        "events.product_id": {
            "invalid_non_null_refs": invalid_product,
            "passed": invalid_product == 0,
        },
        "events.order_id": {
            "invalid_non_null_refs": invalid_order,
            "passed": invalid_order == 0,
        },
    }

    quality = {
        "total_raw_event_rows": rows,
        "unique_event_ids": rows - duplicates,
        "duplicate_event_rows": duplicates,
        "duplicate_event_rate_pct": pct(duplicates, rows),
        "late_over_1h_rows": late_1h,
        "late_over_1h_rate_pct": pct(late_1h, rows),
        "late_over_24h_rows": late_24h,
        "late_over_24h_rate_pct": pct(late_24h, rows),
        "negative_ingestion_lag_rows": negative_lag,
        "event_type_distribution": dict(
            sorted(event_types.items(), key=lambda x: x[1], reverse=True)
        ),
        "passed": negative_lag == 0,
    }
    return pk, fk, quality


def main():
    args = parse_args()
    report_path = args.report or (args.input_dir / "validation_report_fast.json")

    missing = []
    for name in REQUIRED_FILES:
        path = args.input_dir / name
        if name == "manifest.json":
            if not path.exists():
                missing.append(name)
        elif not path.exists() and not path.with_suffix(".parquet").exists():
            missing.append(name)
    if missing:
        report = {"passed": False, "file_presence": {"passed": False, "missing_files": missing}}
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        raise SystemExit(1)

    manifest = json.loads((args.input_dir / "manifest.json").read_text(encoding="utf-8"))
    counts = manifest["row_counts"]

    primary_keys = {}
    foreign_keys = {}

    customer_pk, profiles = validate_customer_profiles(args.input_dir, counts["customers"])
    primary_keys["customers.csv"] = customer_pk

    identity_pk, identity_fk = validate_identities(args.input_dir, counts)
    primary_keys["identities.csv"] = identity_pk
    foreign_keys["identities.customer_id"] = identity_fk

    primary_keys["products.csv"] = validate_simple_pk(
        args.input_dir / "products.csv", "product_id", counts["products"]
    )

    order_pks, order_fks, reconciliation = reconcile_orders(
        args.input_dir, counts, args.reconciliation_tolerance
    )
    primary_keys.update(order_pks)
    foreign_keys.update(order_fks)

    ticket_pk, ticket_fks = validate_support(args.input_dir, counts)
    primary_keys["support_tickets.csv"] = ticket_pk
    foreign_keys.update(ticket_fks)

    session_pk, session_fks = validate_sessions(args.input_dir, counts)
    primary_keys["sessions.csv"] = session_pk
    foreign_keys.update(session_fks)

    event_pk, event_fks, event_quality = validate_events(args.input_dir, counts)
    primary_keys["events.csv"] = event_pk
    foreign_keys.update(event_fks)

    passed = (
        all(v["passed"] for v in primary_keys.values())
        and all(v["passed"] for v in foreign_keys.values())
        and reconciliation["passed"]
        and event_quality["passed"]
    )

    report = {
        "dataset_path": str(args.input_dir),
        "validator_mode": "streaming_generator_contract",
        "file_presence": {"passed": True, "missing_files": []},
        "row_counts": counts,
        "primary_keys": primary_keys,
        "foreign_keys": foreign_keys,
        "order_reconciliation": reconciliation,
        "event_quality": event_quality,
        "profile_nulls": profiles,
        "passed": passed,
        "note": (
            "This scale validator relies on the generator's sequential-ID contract "
            "to validate uniqueness and references without materializing large ID sets."
        ),
    }

    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
