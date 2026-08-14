#!/usr/bin/env python3
"""
Generate a realistic synthetic NovaCart CDP dataset.

Outputs:
    customers.csv
    identities.csv
    products.csv
    orders.csv
    order_items.csv
    support_tickets.csv
    sessions.csv
    events.csv

The generator intentionally introduces:
- anonymous activity before identity resolution
- late-arriving events
- duplicate raw events
- null profile attributes
- mixed source timezones
- customer behavior patterns that affect sessions, orders, and support cases

Example:
    python data/generator/generate_synthetic_cdp.py \
        --customers 10000 \
        --products 1000 \
        --output-dir data/generated/dev

Portfolio-scale example:
    python data/generator/generate_synthetic_cdp.py \
        --customers 100000 \
        --products 1000 \
        --avg-orders 5 \
        --avg-browsing-sessions 6 \
        --output-dir data/generated/full
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

import numpy as np
from faker import Faker


NOW_UTC = datetime(2026, 8, 13, 23, 0, 0, tzinfo=timezone.utc)

TIMEZONES = [
    "America/Los_Angeles",
    "America/Denver",
    "America/Chicago",
    "America/New_York",
    "Europe/London",
    "Europe/Berlin",
    "Asia/Kolkata",
    "Australia/Sydney",
]

COUNTRY_BY_TZ = {
    "America/Los_Angeles": "US",
    "America/Denver": "US",
    "America/Chicago": "US",
    "America/New_York": "US",
    "Europe/London": "GB",
    "Europe/Berlin": "DE",
    "Asia/Kolkata": "IN",
    "Australia/Sydney": "AU",
}

BEHAVIOR_SEGMENTS = (
    ("stable", 0.55),
    ("declining_engagement", 0.20),
    ("support_issue", 0.12),
    ("price_sensitive", 0.08),
    ("dormant", 0.05),
)

PRODUCT_TAXONOMY = {
    "Electronics": ["Audio", "Smart Home", "Accessories", "Wearables"],
    "Home": ["Kitchen", "Bedding", "Decor", "Storage"],
    "Apparel": ["Tops", "Bottoms", "Shoes", "Outerwear"],
    "Beauty": ["Skincare", "Haircare", "Makeup", "Fragrance"],
    "Sports": ["Fitness", "Outdoor", "Running", "Recovery"],
    "Pets": ["Food", "Toys", "Grooming", "Accessories"],
}

BRANDS = [
    "NovaBasics", "NorthPeak", "Luma", "Everfield", "Orbit", "Cedar & Co",
    "Harbor", "Vela", "Aster", "SummitWorks",
]

EVENT_FUNNELS = [
    ["page_view", "product_view"],
    ["page_view", "search", "product_view"],
    ["page_view", "product_view", "add_to_cart"],
    ["page_view", "search", "product_view", "add_to_cart", "checkout_started"],
]

SUPPORT_CATEGORIES = [
    "shipping_delay",
    "damaged_item",
    "refund_request",
    "payment_issue",
    "product_question",
    "account_issue",
]

SUPPORT_SUBJECTS = {
    "shipping_delay": "Order has not arrived",
    "damaged_item": "Item arrived damaged",
    "refund_request": "Requesting a refund",
    "payment_issue": "Problem with payment",
    "product_question": "Question about a product",
    "account_issue": "Unable to access account",
}


@dataclass
class Config:
    customers: int
    products: int
    campaigns: int
    avg_orders: float
    avg_browsing_sessions: float
    duplicate_event_rate: float
    late_event_rate: float
    null_profile_rate: float
    seed: int
    output_dir: Path
    output_format: str


def parse_args() -> Config:
    parser = argparse.ArgumentParser(description="Generate NovaCart synthetic CDP data.")
    parser.add_argument("--customers", type=int, default=10_000)
    parser.add_argument("--products", type=int, default=1_000)
    parser.add_argument("--campaigns", type=int, default=60)
    parser.add_argument("--avg-orders", type=float, default=5.0)
    parser.add_argument("--avg-browsing-sessions", type=float, default=6.0)
    parser.add_argument("--duplicate-event-rate", type=float, default=0.01)
    parser.add_argument("--late-event-rate", type=float, default=0.04)
    parser.add_argument("--null-profile-rate", type=float, default=0.03)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=Path("data/generated/dev"))
    parser.add_argument(
        "--output-format",
        choices=["csv", "parquet"],
        default="csv",
        help=(
            "CSV is dependency-free. Parquet requires pyarrow and writes "
            "streaming Parquet row groups directly without first creating CSV."
        ),
    )
    args = parser.parse_args()
    return Config(
        customers=args.customers,
        products=args.products,
        campaigns=args.campaigns,
        avg_orders=args.avg_orders,
        avg_browsing_sessions=args.avg_browsing_sessions,
        duplicate_event_rate=args.duplicate_event_rate,
        late_event_rate=args.late_event_rate,
        null_profile_rate=args.null_profile_rate,
        seed=args.seed,
        output_dir=args.output_dir,
        output_format=args.output_format,
    )


def iso(dt: Optional[datetime]) -> str:
    return "" if dt is None else dt.isoformat(timespec="seconds")


def weighted_choice(rng: random.Random, values: Sequence[Tuple[str, float]]) -> str:
    r = rng.random()
    running = 0.0
    for value, weight in values:
        running += weight
        if r <= running:
            return value
    return values[-1][0]


def bounded_poisson(np_rng: np.random.Generator, lam: float, minimum: int = 0, maximum: Optional[int] = None) -> int:
    value = max(minimum, int(np_rng.poisson(max(0.01, lam))))
    if maximum is not None:
        value = min(value, maximum)
    return value


def random_utc_between(rng: random.Random, start: datetime, end: datetime) -> datetime:
    seconds = max(1, int((end - start).total_seconds()))
    return start + timedelta(seconds=rng.randrange(seconds))


def customer_activity_time(
    rng: random.Random,
    created_at: datetime,
    segment: str,
) -> datetime:
    """Draw activity times so latent behavior patterns emerge from the rows."""
    start = max(created_at, NOW_UTC - timedelta(days=365))
    split_recent = NOW_UTC - timedelta(days=60)

    if split_recent <= start:
        return random_utc_between(rng, start, NOW_UTC)

    if segment == "declining_engagement":
        # Create an observable decline across the exact 60-day windows used by
        # semantic validation. Most activity falls in the prior 60-day period,
        # materially less falls in the recent 60-day period, and the remainder
        # is older historical activity.
        prior_start = NOW_UTC - timedelta(days=120)

        # If the customer is too new for both comparison windows, use whatever
        # history is available without fabricating pre-creation activity.
        if start >= split_recent:
            return random_utc_between(rng, start, NOW_UTC)

        draw = rng.random()

        if prior_start >= start:
            if draw < 0.60:
                return random_utc_between(rng, prior_start, split_recent)
            if draw < 0.78:
                return random_utc_between(rng, split_recent, NOW_UTC)
            return random_utc_between(rng, start, prior_start)

        # Customer was created inside the prior comparison window.
        if draw < 0.72:
            return random_utc_between(rng, start, split_recent)
        return random_utc_between(rng, split_recent, NOW_UTC)

    if segment == "dormant":
        dormant_cutoff = NOW_UTC - timedelta(days=90)
        if dormant_cutoff > start:
            return random_utc_between(rng, start, dormant_cutoff)
        return random_utc_between(rng, start, NOW_UTC)

    if segment == "support_issue":
        # Still active, but activity begins thinning after a recent service problem.
        if rng.random() < 0.62:
            return random_utc_between(rng, start, split_recent)
        return random_utc_between(rng, split_recent, NOW_UTC)

    # Stable and price-sensitive customers remain active recently.
    if rng.random() < 0.58:
        return random_utc_between(rng, split_recent, NOW_UTC)
    return random_utc_between(rng, start, split_recent)


class TableWriter:
    """Writer abstraction supporting CSV or direct batched Parquet."""

    def __init__(
        self,
        path: Path,
        fieldnames: Sequence[str],
        output_format: str,
        batch_size: int = 10_000,
    ):
        self.fieldnames = list(fieldnames)
        self.output_format = output_format
        self.batch_size = batch_size
        self.rows_written = 0
        self._csv_handle = None
        self._csv_writer = None
        self._buffer = []
        self._parquet_writer = None
        self._schema = None

        if output_format == "csv":
            self.path = path.with_suffix(".csv")
            self._csv_handle = self.path.open(
                "w",
                newline="",
                encoding="utf-8",
                buffering=4 * 1024 * 1024,
            )
            self._csv_writer = csv.DictWriter(
                self._csv_handle,
                fieldnames=self.fieldnames,
            )
            self._csv_writer.writeheader()
        elif output_format == "parquet":
            try:
                import pyarrow as pa
                import pyarrow.parquet as pq
            except ImportError as exc:
                raise RuntimeError(
                    "Parquet output requires pyarrow. Install it with "
                    "`pip install pyarrow`, or run with --output-format csv."
                ) from exc
            self._pa = pa
            self._pq = pq
            self.path = path.with_suffix(".parquet")
        else:
            raise ValueError(f"Unsupported output format: {output_format}")

    def writerow(self, row: dict) -> None:
        if self.output_format == "csv":
            self._csv_writer.writerow(row)
        else:
            normalized = {
                field: (None if row.get(field) == "" else row.get(field))
                for field in self.fieldnames
            }
            self._buffer.append(normalized)
            if len(self._buffer) >= self.batch_size:
                self._flush_parquet()

        self.rows_written += 1

    def _flush_parquet(self) -> None:
        if not self._buffer:
            return

        if self._schema is None:
            table = self._pa.Table.from_pylist(self._buffer)
            self._schema = table.schema
            self._parquet_writer = self._pq.ParquetWriter(
                self.path,
                self._schema,
                compression="snappy",
            )
        else:
            table = self._pa.Table.from_pylist(
                self._buffer,
                schema=self._schema,
            )

        self._parquet_writer.write_table(table)
        self._buffer.clear()

    def close(self) -> None:
        if self.output_format == "csv":
            if self._csv_handle is not None:
                self._csv_handle.close()
            return

        self._flush_parquet()
        if self._parquet_writer is not None:
            self._parquet_writer.close()


def open_writer(
    path: Path,
    fieldnames: Sequence[str],
    output_format: str,
):
    writer = TableWriter(path, fieldnames, output_format)
    return writer, writer


TRUTH_EXPECTATIONS = {
    "stable": {
        "expected_recent_activity": "active",
        "expected_purchase_pattern": "stable_or_growing",
        "expected_support_pattern": "baseline",
        "expected_discount_pattern": "baseline",
    },
    "declining_engagement": {
        "expected_recent_activity": "declining",
        "expected_purchase_pattern": "recent_lower_than_prior",
        "expected_support_pattern": "baseline",
        "expected_discount_pattern": "baseline",
    },
    "support_issue": {
        "expected_recent_activity": "declining_or_mixed",
        "expected_purchase_pattern": "recent_lower_or_mixed",
        "expected_support_pattern": "recent_negative_or_unresolved",
        "expected_discount_pattern": "baseline",
    },
    "price_sensitive": {
        "expected_recent_activity": "active",
        "expected_purchase_pattern": "active",
        "expected_support_pattern": "baseline",
        "expected_discount_pattern": "elevated",
    },
    "dormant": {
        "expected_recent_activity": "very_low",
        "expected_purchase_pattern": "little_or_no_recent_purchase",
        "expected_support_pattern": "low",
        "expected_discount_pattern": "low_or_baseline",
    },
}


def write_generation_truth(config: Config, customers) -> int:
    """
    Persist generator-only labels separately from production-like CDP tables.

    SignalDesk application code must never read this file. It exists only for
    generator validation, semantic tests, and future evaluation-dataset creation.
    """
    truth_dir = config.output_dir / "_truth"
    truth_dir.mkdir(parents=True, exist_ok=True)

    fields = [
        "customer_id",
        "synthetic_segment",
        "expected_recent_activity",
        "expected_purchase_pattern",
        "expected_support_pattern",
        "expected_discount_pattern",
    ]

    handle, writer = open_writer(
        truth_dir / "customer_generation_truth.csv",
        fields,
        config.output_format,
    )

    count = 0
    for customer in customers:
        segment = customer["segment"]
        expected = TRUTH_EXPECTATIONS[segment]
        writer.writerow({
            "customer_id": customer["customer_id"],
            "synthetic_segment": segment,
            **expected,
        })
        count += 1

    handle.close()
    return count

LOCATION_POOLS = {
    "America/Los_Angeles": [
        ("CA", "Los Angeles", "90001"),
        ("CA", "San Francisco", "94105"),
        ("WA", "Seattle", "98101"),
        ("OR", "Portland", "97205"),
    ],
    "America/Denver": [
        ("CO", "Denver", "80202"),
        ("UT", "Salt Lake City", "84101"),
        ("AZ", "Phoenix", "85004"),
    ],
    "America/Chicago": [
        ("IL", "Chicago", "60601"),
        ("TX", "Austin", "78701"),
        ("MN", "Minneapolis", "55401"),
    ],
    "America/New_York": [
        ("NY", "New York", "10001"),
        ("MA", "Boston", "02108"),
        ("PA", "Philadelphia", "19103"),
    ],
    "Europe/London": [
        ("England", "London", "EC1A 1BB"),
        ("England", "Manchester", "M1 1AE"),
    ],
    "Europe/Berlin": [
        ("Berlin", "Berlin", "10115"),
        ("Bavaria", "Munich", "80331"),
    ],
    "Asia/Kolkata": [
        ("Maharashtra", "Mumbai", "400001"),
        ("Karnataka", "Bengaluru", "560001"),
        ("Delhi", "New Delhi", "110001"),
    ],
    "Australia/Sydney": [
        ("NSW", "Sydney", "2000"),
        ("VIC", "Melbourne", "3000"),
    ],
}

FIRST_NAMES = [
    "Ava", "Liam", "Maya", "Noah", "Priya", "Ethan", "Sofia", "Arjun",
    "Emma", "Leo", "Nina", "Owen", "Zara", "Daniel", "Mila", "Ryan",
]
LAST_NAMES = [
    "Patel", "Smith", "Johnson", "Garcia", "Lee", "Brown", "Kumar", "Wilson",
    "Davis", "Martin", "Anderson", "Thomas", "Nguyen", "Clark", "Taylor", "Moore",
]


def synthetic_phone(i: int, country: str) -> str:
    # Deterministic unique-looking numbers; not intended to be dialable.
    if country == "US":
        return f"+1-555-{(i // 10000) % 1000:03d}-{i % 10000:04d}"
    return f"+99-555-{i:09d}"


def synthetic_dob(rng: random.Random) -> str:
    age_days = rng.randint(18 * 365, 80 * 365)
    return (NOW_UTC.date() - timedelta(days=age_days)).isoformat()



CAMPAIGN_TYPES = ["PROMOTIONAL", "WINBACK", "LOYALTY", "NEW_ARRIVAL", "SERVICE"]
CAMPAIGN_CHANNELS = ["EMAIL", "SMS", "PUSH"]

CONSENT_CHANNELS = ["EMAIL", "SMS", "PUSH"]

SUBSCRIPTION_TYPES = [
    "NEWSLETTER",
    "LOYALTY_PROGRAM",
    "REPLENISHMENT",
]

SEGMENT_CAMPAIGN_PROFILE = {
    "stable": {
        "open_rate": 0.42,
        "click_rate_given_open": 0.24,
        "conversion_rate_given_click": 0.12,
        "recent_exposure_multiplier": 1.0,
    },
    "declining_engagement": {
        "open_rate": 0.20,
        "click_rate_given_open": 0.14,
        "conversion_rate_given_click": 0.07,
        "recent_exposure_multiplier": 0.75,
    },
    "support_issue": {
        "open_rate": 0.31,
        "click_rate_given_open": 0.15,
        "conversion_rate_given_click": 0.06,
        "recent_exposure_multiplier": 0.85,
    },
    "price_sensitive": {
        "open_rate": 0.58,
        "click_rate_given_open": 0.48,
        "conversion_rate_given_click": 0.25,
        "recent_exposure_multiplier": 1.15,
    },
    "dormant": {
        "open_rate": 0.08,
        "click_rate_given_open": 0.06,
        "conversion_rate_given_click": 0.02,
        "recent_exposure_multiplier": 0.35,
    },
}


def generate_campaigns(config: Config, rng: random.Random):
    fields = [
        "campaign_id",
        "campaign_name",
        "campaign_type",
        "channel",
        "start_at",
        "end_at",
        "offer_code",
        "discount_pct",
        "audience_type",
        "active",
    ]
    handle, writer = open_writer(
        config.output_dir / "campaigns.csv",
        fields,
        config.output_format,
    )
    campaigns = []

    for i in range(1, config.campaigns + 1):
        campaign_type = rng.choice(CAMPAIGN_TYPES)
        channel = rng.choice(CAMPAIGN_CHANNELS)
        start_at = random_utc_between(
            rng,
            NOW_UTC - timedelta(days=365),
            NOW_UTC - timedelta(days=3),
        )
        duration_days = rng.randint(7, 45)
        end_at = min(NOW_UTC + timedelta(days=30), start_at + timedelta(days=duration_days))

        discount_pct = 0
        offer_code = ""
        if campaign_type in {"PROMOTIONAL", "WINBACK", "LOYALTY"}:
            discount_pct = rng.choice([5, 10, 15, 20])
            offer_code = f"CMP{i:04d}-{discount_pct}"

        row = {
            "campaign_id": f"CAM{i:06d}",
            "campaign_name": f"{campaign_type.title().replace('_', ' ')} {i:03d}",
            "campaign_type": campaign_type,
            "channel": channel,
            "start_at": iso(start_at),
            "end_at": iso(end_at),
            "offer_code": offer_code,
            "discount_pct": discount_pct,
            "audience_type": rng.choice(
                ["ALL_ACTIVE", "AT_RISK", "LOYALTY", "CATEGORY_INTEREST", "WINBACK"]
            ),
            "active": start_at <= NOW_UTC <= end_at,
        }
        writer.writerow(row)
        campaigns.append({
            **row,
            "_start_at": start_at,
            "_end_at": end_at,
        })

    handle.close()
    return campaigns


def generate_consent_preferences(config: Config, customers, rng: random.Random):
    fields = [
        "consent_id",
        "customer_id",
        "channel",
        "status",
        "updated_at",
        "source",
    ]
    handle, writer = open_writer(
        config.output_dir / "consent_preferences.csv",
        fields,
        config.output_format,
    )

    consent_by_customer = {}
    consent_counter = 1

    channel_opt_in = {
        "EMAIL": 0.86,
        "SMS": 0.61,
        "PUSH": 0.69,
    }

    for customer in customers:
        customer_id = customer["customer_id"]
        consent_by_customer[customer_id] = {}

        for channel in CONSENT_CHANNELS:
            opted_in = rng.random() < channel_opt_in[channel]
            # A small fraction explicitly opts out recently.
            if opted_in and rng.random() < 0.08:
                status = "OPTED_OUT"
                updated_at = random_utc_between(
                    rng,
                    max(customer["created_at"], NOW_UTC - timedelta(days=120)),
                    NOW_UTC,
                )
            else:
                status = "OPTED_IN" if opted_in else "OPTED_OUT"
                updated_at = random_utc_between(
                    rng,
                    customer["created_at"],
                    NOW_UTC,
                )

            row = {
                "consent_id": f"CN{consent_counter:09d}",
                "customer_id": customer_id,
                "channel": channel,
                "status": status,
                "updated_at": iso(updated_at),
                "source": rng.choice(["ACCOUNT_SETTINGS", "CHECKOUT", "SIGNUP", "SUPPORT"]),
            }
            writer.writerow(row)
            consent_by_customer[customer_id][channel] = {
                "status": status,
                "updated_at": updated_at,
            }
            consent_counter += 1

    handle.close()
    return consent_by_customer, consent_counter - 1


def generate_subscriptions(config: Config, customers, rng: random.Random):
    fields = [
        "subscription_id",
        "customer_id",
        "subscription_type",
        "status",
        "started_at",
        "ended_at",
        "renewal_at",
    ]
    handle, writer = open_writer(
        config.output_dir / "subscriptions.csv",
        fields,
        config.output_format,
    )

    subscription_counter = 1

    segment_probability = {
        "stable": 0.44,
        "declining_engagement": 0.31,
        "support_issue": 0.34,
        "price_sensitive": 0.52,
        "dormant": 0.12,
    }

    for customer in customers:
        if rng.random() > segment_probability[customer["segment"]]:
            continue

        n_subs = 1 if rng.random() < 0.88 else 2
        chosen = rng.sample(SUBSCRIPTION_TYPES, k=min(n_subs, len(SUBSCRIPTION_TYPES)))

        for sub_type in chosen:
            started_at = random_utc_between(
                rng,
                customer["created_at"],
                max(customer["created_at"] + timedelta(seconds=1), NOW_UTC),
            )

            if customer["segment"] == "dormant":
                status = rng.choices(["ACTIVE", "CANCELED", "PAUSED"], [0.15, 0.70, 0.15])[0]
            elif customer["segment"] == "declining_engagement":
                status = rng.choices(["ACTIVE", "CANCELED", "PAUSED"], [0.58, 0.25, 0.17])[0]
            else:
                status = rng.choices(["ACTIVE", "CANCELED", "PAUSED"], [0.78, 0.14, 0.08])[0]

            ended_at = ""
            renewal_at = ""
            if status == "CANCELED":
                end_dt = min(
                    NOW_UTC,
                    started_at + timedelta(days=rng.randint(30, 365)),
                )
                ended_at = iso(end_dt)
            elif status == "ACTIVE":
                renewal_at = iso(NOW_UTC + timedelta(days=rng.randint(1, 90)))

            writer.writerow({
                "subscription_id": f"SUB{subscription_counter:09d}",
                "customer_id": customer["customer_id"],
                "subscription_type": sub_type,
                "status": status,
                "started_at": iso(started_at),
                "ended_at": ended_at,
                "renewal_at": renewal_at,
            })
            subscription_counter += 1

    handle.close()
    return subscription_counter - 1


def generate_campaign_exposures(
    config: Config,
    customers,
    campaigns,
    consent_by_customer,
    orders_by_customer,
    rng: random.Random,
    np_rng: np.random.Generator,
):
    fields = [
        "exposure_id",
        "customer_id",
        "campaign_id",
        "channel",
        "sent_at",
        "delivery_status",
        "opened_at",
        "clicked_at",
        "converted_order_id",
    ]
    handle, writer = open_writer(
        config.output_dir / "campaign_exposures.csv",
        fields,
        config.output_format,
    )

    exposure_counter = 1

    for customer in customers:
        profile = SEGMENT_CAMPAIGN_PROFILE[customer["segment"]]
        n_exposures = bounded_poisson(
            np_rng,
            4.5 * profile["recent_exposure_multiplier"],
            minimum=0,
            maximum=16,
        )

        eligible_campaigns = [
            c for c in campaigns
            if c["_end_at"] >= customer["created_at"]
        ]
        if not eligible_campaigns:
            continue

        chosen_campaigns = (
            rng.sample(eligible_campaigns, k=min(n_exposures, len(eligible_campaigns)))
            if n_exposures
            else []
        )

        for campaign in chosen_campaigns:
            send_start = max(customer["created_at"], campaign["_start_at"])
            send_end = min(NOW_UTC, campaign["_end_at"])
            if send_end <= send_start:
                continue

            sent_at = random_utc_between(rng, send_start, send_end)
            channel = campaign["channel"]
            consent = consent_by_customer[customer["customer_id"]][channel]

            # Deterministic consent rule: if the customer had opted out by send time,
            # no send occurs. This is deliberately enforced outside probabilistic logic.
            if (
                consent["status"] == "OPTED_OUT"
                and consent["updated_at"] <= sent_at
            ):
                continue

            delivery_status = rng.choices(
                ["DELIVERED", "BOUNCED", "FAILED"],
                [0.965, 0.02, 0.015],
            )[0]

            opened_at = ""
            clicked_at = ""
            converted_order_id = ""

            if delivery_status == "DELIVERED":
                opened = rng.random() < profile["open_rate"]
                if opened:
                    open_dt = min(NOW_UTC, sent_at + timedelta(minutes=rng.randint(1, 2880)))
                    opened_at = iso(open_dt)

                    clicked = rng.random() < profile["click_rate_given_open"]
                    if clicked:
                        click_dt = min(NOW_UTC, open_dt + timedelta(minutes=rng.randint(1, 720)))
                        clicked_at = iso(click_dt)

                        if rng.random() < profile["conversion_rate_given_click"]:
                            later_orders = [
                                o for o in orders_by_customer.get(customer["customer_id"], [])
                                if o[1] >= click_dt and o[2] != "CANCELED"
                            ]
                            if later_orders:
                                converted_order_id = rng.choice(later_orders)[0]

            writer.writerow({
                "exposure_id": f"EXP{exposure_counter:010d}",
                "customer_id": customer["customer_id"],
                "campaign_id": campaign["campaign_id"],
                "channel": channel,
                "sent_at": iso(sent_at),
                "delivery_status": delivery_status,
                "opened_at": opened_at,
                "clicked_at": clicked_at,
                "converted_order_id": converted_order_id,
            })
            exposure_counter += 1

    handle.close()
    return exposure_counter - 1

def generate_products(config: Config, rng: random.Random, fake: Faker):
    fields = [
        "product_id", "sku", "product_name", "category", "subcategory",
        "brand", "base_price", "cost", "active", "created_at",
    ]
    handle, writer = open_writer(config.output_dir / "products.csv", fields, config.output_format)
    products = []

    categories = list(PRODUCT_TAXONOMY.keys())
    for i in range(1, config.products + 1):
        category = rng.choice(categories)
        subcategory = rng.choice(PRODUCT_TAXONOMY[category])
        price = round(math.exp(rng.uniform(math.log(8), math.log(450))), 2)
        cost = round(price * rng.uniform(0.35, 0.72), 2)
        product = {
            "product_id": f"P{i:06d}",
            "sku": f"SKU-{i:07d}",
            "product_name": f"{rng.choice(BRANDS)} {subcategory} {fake.word().title()}",
            "category": category,
            "subcategory": subcategory,
            "brand": rng.choice(BRANDS),
            "base_price": price,
            "cost": cost,
            "active": rng.random() > 0.03,
            "created_at": iso(random_utc_between(rng, NOW_UTC - timedelta(days=1500), NOW_UTC - timedelta(days=30))),
        }
        writer.writerow(product)
        products.append(product)

    handle.close()
    return products


def generate_customers_and_identities(
    config: Config,
    rng: random.Random,
    np_rng: np.random.Generator,
    fake: Faker,
):
    customer_fields = [
        "customer_id", "created_at", "first_name", "last_name", "email", "phone",
        "country", "state", "city", "postal_code", "date_of_birth",
        "loyalty_tier", "customer_status", "timezone", "first_seen_at", "last_seen_at",
    ]
    identity_fields = [
        "identity_id", "customer_id", "identity_type", "identity_value",
        "is_primary", "first_seen_at", "last_seen_at", "resolved_at", "resolution_method",
    ]

    ch, cw = open_writer(config.output_dir / "customers.csv", customer_fields, config.output_format)
    ih, iw = open_writer(config.output_dir / "identities.csv", identity_fields, config.output_format)

    customers = []
    cookie_identity = {}
    identity_counter = 1

    for i in range(1, config.customers + 1):
        customer_id = f"C{i:07d}"
        tz_name = rng.choice(TIMEZONES)
        created_at = random_utc_between(rng, NOW_UTC - timedelta(days=1100), NOW_UTC - timedelta(days=45))
        segment = weighted_choice(rng, BEHAVIOR_SEGMENTS)

        first_name = rng.choice(FIRST_NAMES)
        last_name = rng.choice(LAST_NAMES)
        email = f"{first_name}.{last_name}.{i}@example.com".lower()
        country = COUNTRY_BY_TZ[tz_name]
        state, city, postal = rng.choice(LOCATION_POOLS[tz_name])
        phone = synthetic_phone(i, country)
        dob = synthetic_dob(rng)

        def maybe_null(value):
            return "" if rng.random() < config.null_profile_rate else value

        last_seen = customer_activity_time(rng, created_at, segment)
        if last_seen < created_at:
            last_seen = created_at

        row = {
            "customer_id": customer_id,
            "created_at": iso(created_at),
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": maybe_null(phone),
            "country": COUNTRY_BY_TZ[tz_name],
            "state": maybe_null(state),
            "city": maybe_null(city),
            "postal_code": maybe_null(postal),
            "date_of_birth": maybe_null(dob),
            "loyalty_tier": rng.choices(["NONE", "SILVER", "GOLD", "PLATINUM"], [0.48, 0.28, 0.18, 0.06])[0],
            "customer_status": rng.choices(["ACTIVE", "ACTIVE", "ACTIVE", "PAUSED", "CLOSED"], [0.25, 0.25, 0.25, 0.18, 0.07])[0],
            "timezone": tz_name,
            "first_seen_at": iso(created_at),
            "last_seen_at": iso(last_seen),
        }
        cw.writerow(row)

        # Email identity
        email_identity_id = f"I{identity_counter:09d}"
        identity_counter += 1
        iw.writerow({
            "identity_id": email_identity_id,
            "customer_id": customer_id,
            "identity_type": "email",
            "identity_value": email,
            "is_primary": True,
            "first_seen_at": iso(created_at),
            "last_seen_at": iso(last_seen),
            "resolved_at": iso(created_at),
            "resolution_method": "registration",
        })

        # Optional phone identity
        if row["phone"]:
            phone_identity_id = f"I{identity_counter:09d}"
            identity_counter += 1
            iw.writerow({
                "identity_id": phone_identity_id,
                "customer_id": customer_id,
                "identity_type": "phone",
                "identity_value": row["phone"],
                "is_primary": False,
                "first_seen_at": iso(created_at),
                "last_seen_at": iso(last_seen),
                "resolved_at": iso(created_at),
                "resolution_method": "profile",
            })

        # Cookie identity can have historical sessions before it was resolved.
        cookie_id = f"I{identity_counter:09d}"
        identity_counter += 1
        cookie_first = max(NOW_UTC - timedelta(days=365), created_at - timedelta(days=rng.randint(0, 120)))
        cookie_resolved = min(NOW_UTC, created_at + timedelta(days=rng.randint(0, 45)))
        cookie_last = max(last_seen, cookie_resolved)
        iw.writerow({
            "identity_id": cookie_id,
            "customer_id": customer_id,
            "identity_type": "cookie_id",
            "identity_value": f"cookie_{rng.getrandbits(64):016x}",
            "is_primary": False,
            "first_seen_at": iso(cookie_first),
            "last_seen_at": iso(cookie_last),
            "resolved_at": iso(cookie_resolved),
            "resolution_method": rng.choice(["login", "checkout", "email_link"]),
        })

        customers.append({
            "customer_id": customer_id,
            "created_at": created_at,
            "timezone": tz_name,
            "segment": segment,
            "cookie_identity_id": cookie_id,
            "cookie_resolved_at": cookie_resolved,
        })
        cookie_identity[customer_id] = cookie_id

    ch.close()
    ih.close()
    return customers, identity_counter - 1


def generate_orders(
    config: Config,
    customers,
    products,
    rng: random.Random,
    np_rng: np.random.Generator,
):
    order_fields = [
        "order_id", "customer_id", "order_timestamp", "status", "channel",
        "currency", "subtotal", "discount_amount", "tax_amount",
        "shipping_amount", "total_amount", "promotion_code",
    ]
    item_fields = [
        "order_item_id", "order_id", "product_id", "quantity",
        "unit_price", "line_discount", "line_total",
    ]
    oh, ow = open_writer(config.output_dir / "orders.csv", order_fields, config.output_format)
    ih, iw = open_writer(config.output_dir / "order_items.csv", item_fields, config.output_format)

    product_lookup = {p["product_id"]: p for p in products}
    product_ids = list(product_lookup)
    orders_by_customer = defaultdict(list)
    order_counter = 1
    item_counter = 1

    segment_multiplier = {
        "stable": 1.05,
        "declining_engagement": 0.85,
        "support_issue": 0.85,
        "price_sensitive": 1.15,
        "dormant": 0.35,
    }

    for customer in customers:
        segment = customer["segment"]
        lam = config.avg_orders * segment_multiplier[segment]
        n_orders = bounded_poisson(np_rng, lam, minimum=0, maximum=max(2, int(config.avg_orders * 4)))

        for _ in range(n_orders):
            order_id = f"O{order_counter:09d}"
            order_counter += 1
            order_ts = customer_activity_time(rng, customer["created_at"], segment)

            if segment == "support_issue":
                status = rng.choices(
                    ["COMPLETED", "SHIPPED", "REFUNDED", "CANCELED"],
                    [0.50, 0.20, 0.20, 0.10],
                )[0]
            else:
                status = rng.choices(
                    ["COMPLETED", "SHIPPED", "REFUNDED", "CANCELED"],
                    [0.72, 0.18, 0.06, 0.04],
                )[0]

            n_items = rng.choices([1, 2, 3, 4], [0.48, 0.30, 0.16, 0.06])[0]
            chosen_products = rng.sample(product_ids, k=min(n_items, len(product_ids)))

            subtotal = 0.0
            discount = 0.0
            item_rows = []
            for product_id in chosen_products:
                product = product_lookup[product_id]
                quantity = rng.choices([1, 2, 3], [0.83, 0.14, 0.03])[0]
                unit_price = round(float(product["base_price"]) * rng.uniform(0.96, 1.04), 2)
                line_subtotal = unit_price * quantity

                discount_rate = 0.0
                if segment == "price_sensitive":
                    discount_rate = rng.choices([0, 0.10, 0.15, 0.20], [0.15, 0.30, 0.30, 0.25])[0]
                elif rng.random() < 0.22:
                    discount_rate = rng.choice([0.05, 0.10, 0.15])

                line_discount = round(line_subtotal * discount_rate, 2)
                line_total = round(line_subtotal - line_discount, 2)
                subtotal += line_subtotal
                discount += line_discount

                item_rows.append({
                    "order_item_id": f"OI{item_counter:010d}",
                    "order_id": order_id,
                    "product_id": product_id,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "line_discount": line_discount,
                    "line_total": line_total,
                })
                item_counter += 1

            subtotal = round(subtotal, 2)
            discount = round(discount, 2)
            taxable = max(0.0, subtotal - discount)
            tax = round(taxable * rng.uniform(0.04, 0.095), 2)
            shipping = 0.0 if taxable >= 75 or rng.random() < 0.35 else round(rng.choice([4.99, 6.99, 9.99]), 2)
            total = round(taxable + tax + shipping, 2)
            promotion_code = ""
            if discount > 0:
                promotion_code = rng.choice(["WELCOME10", "SAVE15", "LOYAL20", "EMAIL10"])

            order_row = {
                "order_id": order_id,
                "customer_id": customer["customer_id"],
                "order_timestamp": iso(order_ts.astimezone(ZoneInfo(customer["timezone"]))),
                "status": status,
                "channel": rng.choices(["WEB", "MOBILE_APP", "MOBILE_WEB"], [0.50, 0.35, 0.15])[0],
                "currency": "USD",
                "subtotal": subtotal,
                "discount_amount": discount,
                "tax_amount": tax,
                "shipping_amount": shipping,
                "total_amount": total,
                "promotion_code": promotion_code,
            }
            ow.writerow(order_row)
            for item_row in item_rows:
                iw.writerow(item_row)

            orders_by_customer[customer["customer_id"]].append(
                (order_id, order_ts, status, total, chosen_products)
            )

    oh.close()
    ih.close()
    return orders_by_customer, order_counter - 1, item_counter - 1


def generate_support_tickets(
    config: Config,
    customers,
    orders_by_customer,
    rng: random.Random,
    np_rng: np.random.Generator,
):
    fields = [
        "ticket_id", "customer_id", "order_id", "opened_at", "closed_at",
        "status", "category", "priority", "channel", "subject", "sentiment", "csat_score",
    ]
    handle, writer = open_writer(config.output_dir / "support_tickets.csv", fields, config.output_format)
    ticket_counter = 1

    ticket_lambda = {
        "stable": 0.07,
        "declining_engagement": 0.12,
        "support_issue": 1.65,
        "price_sensitive": 0.14,
        "dormant": 0.05,
    }

    for customer in customers:
        segment = customer["segment"]
        n_tickets = bounded_poisson(np_rng, ticket_lambda[segment], minimum=0, maximum=6)
        customer_orders = orders_by_customer.get(customer["customer_id"], [])

        for _ in range(n_tickets):
            ticket_id = f"T{ticket_counter:08d}"
            ticket_counter += 1

            if segment == "support_issue" and rng.random() < 0.78:
                opened = random_utc_between(rng, NOW_UTC - timedelta(days=55), NOW_UTC)
                category = rng.choices(
                    ["shipping_delay", "damaged_item", "refund_request", "payment_issue"],
                    [0.40, 0.28, 0.22, 0.10],
                )[0]
                status = rng.choices(["OPEN", "PENDING", "RESOLVED", "CLOSED"], [0.32, 0.24, 0.28, 0.16])[0]
                sentiment = rng.choices(["NEGATIVE", "NEUTRAL", "POSITIVE"], [0.72, 0.24, 0.04])[0]
            else:
                opened = customer_activity_time(rng, customer["created_at"], segment)
                category = rng.choice(SUPPORT_CATEGORIES)
                status = rng.choices(["OPEN", "PENDING", "RESOLVED", "CLOSED"], [0.12, 0.10, 0.40, 0.38])[0]
                sentiment = rng.choices(["NEGATIVE", "NEUTRAL", "POSITIVE"], [0.25, 0.48, 0.27])[0]

            order_id = ""
            if customer_orders and category in {"shipping_delay", "damaged_item", "refund_request", "payment_issue"}:
                eligible = [o for o in customer_orders if o[1] <= opened]
                if eligible:
                    order_id = rng.choice(eligible)[0]

            closed = None
            if status in {"RESOLVED", "CLOSED"}:
                closed = min(NOW_UTC, opened + timedelta(hours=rng.randint(2, 240)))

            if sentiment == "NEGATIVE":
                csat = rng.choice([1, 1, 2, 2, 3]) if closed else ""
            elif sentiment == "POSITIVE":
                csat = rng.choice([4, 5, 5]) if closed else ""
            else:
                csat = rng.choice([3, 3, 4]) if closed else ""

            writer.writerow({
                "ticket_id": ticket_id,
                "customer_id": customer["customer_id"],
                "order_id": order_id,
                "opened_at": iso(opened.astimezone(ZoneInfo(customer["timezone"]))),
                "closed_at": iso(closed.astimezone(ZoneInfo(customer["timezone"]))) if closed else "",
                "status": status,
                "category": category,
                "priority": rng.choices(["LOW", "MEDIUM", "HIGH", "URGENT"], [0.25, 0.48, 0.22, 0.05])[0],
                "channel": rng.choice(["EMAIL", "CHAT", "PHONE", "WEB"]),
                "subject": SUPPORT_SUBJECTS[category],
                "sentiment": sentiment,
                "csat_score": csat,
            })

    handle.close()
    return ticket_counter - 1


def event_received_at(
    rng: random.Random,
    event_time_utc: datetime,
    late_rate: float,
) -> datetime:
    if rng.random() < late_rate:
        return event_time_utc + timedelta(minutes=rng.randint(60, 72 * 60))
    return event_time_utc + timedelta(seconds=rng.randint(1, 300))


def write_event(writer, event_row, rng: random.Random, duplicate_rate: float) -> int:
    writer.writerow(event_row)
    written = 1
    if rng.random() < duplicate_rate:
        # Exact duplicate event ID simulates raw ingestion duplication.
        writer.writerow(event_row)
        written += 1
    return written


def generate_sessions_and_events(
    config: Config,
    customers,
    products,
    orders_by_customer,
    rng: random.Random,
    np_rng: np.random.Generator,
):
    session_fields = [
        "session_id", "customer_id", "identity_id", "session_started_at",
        "session_ended_at", "channel", "device_type", "browser",
        "operating_system", "utm_source", "utm_medium", "utm_campaign",
        "landing_page", "country", "timezone",
    ]
    event_fields = [
        "event_id", "event_type", "event_timestamp", "received_at",
        "customer_id", "identity_id", "session_id", "product_id",
        "order_id", "page_url", "referrer", "event_properties", "source_system",
    ]

    sh, sw = open_writer(config.output_dir / "sessions.csv", session_fields, config.output_format)
    eh, ew = open_writer(config.output_dir / "events.csv", event_fields, config.output_format)

    product_ids = [p["product_id"] for p in products]
    session_counter = 1
    event_counter = 1
    event_rows_written = 0

    session_multiplier = {
        "stable": 1.05,
        "declining_engagement": 0.95,
        "support_issue": 0.90,
        "price_sensitive": 1.25,
        "dormant": 0.35,
    }

    for customer in customers:
        customer_id = customer["customer_id"]
        segment = customer["segment"]
        tz = ZoneInfo(customer["timezone"])
        cookie_identity_id = customer["cookie_identity_id"]
        resolved_at = customer["cookie_resolved_at"]

        # Browsing sessions.
        n_sessions = bounded_poisson(
            np_rng,
            config.avg_browsing_sessions * session_multiplier[segment],
            minimum=0,
            maximum=max(3, int(config.avg_browsing_sessions * 4)),
        )

        for _ in range(n_sessions):
            session_id = f"S{session_counter:010d}"
            session_counter += 1
            started_utc = customer_activity_time(rng, customer["created_at"], segment)
            duration_minutes = max(1, int(np_rng.lognormal(mean=2.2, sigma=0.8)))
            ended_utc = min(NOW_UTC, started_utc + timedelta(minutes=duration_minutes))

            observed_customer_id = customer_id if started_utc >= resolved_at else ""
            channel = rng.choices(["WEB", "MOBILE_APP", "MOBILE_WEB"], [0.52, 0.31, 0.17])[0]
            device = rng.choices(["desktop", "mobile", "tablet"], [0.42, 0.52, 0.06])[0]
            sw.writerow({
                "session_id": session_id,
                "customer_id": observed_customer_id,
                "identity_id": cookie_identity_id,
                "session_started_at": iso(started_utc.astimezone(tz)),
                "session_ended_at": iso(ended_utc.astimezone(tz)),
                "channel": channel,
                "device_type": device,
                "browser": rng.choice(["Chrome", "Safari", "Firefox", "Edge"]),
                "operating_system": rng.choice(["Windows", "macOS", "iOS", "Android", "Linux"]),
                "utm_source": rng.choice(["", "google", "email", "instagram", "direct", "affiliate"]),
                "utm_medium": rng.choice(["", "organic", "cpc", "email", "social", "referral"]),
                "utm_campaign": rng.choice(["", "summer_sale", "loyalty", "winback", "new_arrivals"]),
                "landing_page": rng.choice(["/", "/search", "/category/home", "/category/apparel", "/deals"]),
                "country": COUNTRY_BY_TZ[customer["timezone"]],
                "timezone": customer["timezone"],
            })

            funnel = rng.choice(EVENT_FUNNELS)
            event_time = started_utc
            selected_product = rng.choice(product_ids)
            for event_type in funnel:
                event_id = f"E{event_counter:012d}"
                event_counter += 1
                event_time = min(ended_utc, event_time + timedelta(seconds=rng.randint(10, 180)))
                event_product = selected_product if event_type in {"product_view", "add_to_cart", "remove_from_cart", "checkout_started"} else ""
                page_url = "/"
                if event_product:
                    page_url = f"/product/{event_product}"
                elif event_type == "search":
                    page_url = "/search"

                row = {
                    "event_id": event_id,
                    "event_type": event_type,
                    "event_timestamp": iso(event_time.astimezone(tz)),
                    "received_at": iso(event_received_at(rng, event_time, config.late_event_rate)),
                    "customer_id": observed_customer_id,
                    "identity_id": cookie_identity_id,
                    "session_id": session_id,
                    "product_id": event_product,
                    "order_id": "",
                    "page_url": page_url,
                    "referrer": rng.choice(["", "https://www.google.com", "https://mail.example.com", "https://instagram.com"]),
                    "event_properties": json.dumps(
                        {"position": rng.randint(1, 20)} if event_type == "search" else {},
                        separators=(",", ":"),
                    ),
                    "source_system": channel.lower(),
                }
                event_rows_written += write_event(ew, row, rng, config.duplicate_event_rate)

        # Purchase sessions ensure order and behavioral data reconcile.
        for order_id, order_ts, status, total, ordered_products in orders_by_customer.get(customer_id, []):
            if status == "CANCELED" or rng.random() > 0.88:
                continue

            session_id = f"S{session_counter:010d}"
            session_counter += 1
            started_utc = max(customer["created_at"], order_ts - timedelta(minutes=rng.randint(5, 45)))
            ended_utc = min(NOW_UTC, order_ts + timedelta(minutes=rng.randint(1, 8)))
            observed_customer_id = customer_id if started_utc >= resolved_at else ""

            sw.writerow({
                "session_id": session_id,
                "customer_id": observed_customer_id,
                "identity_id": cookie_identity_id,
                "session_started_at": iso(started_utc.astimezone(tz)),
                "session_ended_at": iso(ended_utc.astimezone(tz)),
                "channel": rng.choice(["WEB", "MOBILE_APP"]),
                "device_type": rng.choice(["desktop", "mobile"]),
                "browser": rng.choice(["Chrome", "Safari", "Firefox", "Edge"]),
                "operating_system": rng.choice(["Windows", "macOS", "iOS", "Android"]),
                "utm_source": rng.choice(["direct", "email", "google", ""]),
                "utm_medium": rng.choice(["direct", "email", "cpc", ""]),
                "utm_campaign": rng.choice(["", "loyalty", "winback", "summer_sale"]),
                "landing_page": "/",
                "country": COUNTRY_BY_TZ[customer["timezone"]],
                "timezone": customer["timezone"],
            })

            sequence = [
                ("product_view", ordered_products[0] if ordered_products else ""),
                ("add_to_cart", ordered_products[0] if ordered_products else ""),
                ("checkout_started", ordered_products[0] if ordered_products else ""),
                ("purchase_completed", ""),
            ]
            event_time = started_utc
            for event_type, product_id in sequence:
                event_id = f"E{event_counter:012d}"
                event_counter += 1
                if event_type == "purchase_completed":
                    event_time = order_ts
                else:
                    event_time = min(order_ts, event_time + timedelta(seconds=rng.randint(20, 240)))

                row = {
                    "event_id": event_id,
                    "event_type": event_type,
                    "event_timestamp": iso(event_time.astimezone(tz)),
                    "received_at": iso(event_received_at(rng, event_time, config.late_event_rate)),
                    "customer_id": observed_customer_id,
                    "identity_id": cookie_identity_id,
                    "session_id": session_id,
                    "product_id": product_id,
                    "order_id": order_id if event_type == "purchase_completed" else "",
                    "page_url": "/checkout" if event_type in {"checkout_started", "purchase_completed"} else f"/product/{product_id}",
                    "referrer": "",
                    "event_properties": json.dumps(
                        {"order_total": total} if event_type == "purchase_completed" else {},
                        separators=(",", ":"),
                    ),
                    "source_system": "commerce_web",
                }
                event_rows_written += write_event(ew, row, rng, config.duplicate_event_rate)

    sh.close()
    eh.close()
    return session_counter - 1, event_counter - 1, event_rows_written


def count_csv_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8") as f:
        return max(0, sum(1 for _ in f) - 1)


def main():
    config = parse_args()
    config.output_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(config.seed)
    np_rng = np.random.default_rng(config.seed)
    Faker.seed(config.seed)
    fake = Faker()

    start = time.perf_counter()

    products = generate_products(config, rng, fake)
    campaigns = generate_campaigns(config, rng)
    customers, n_identities = generate_customers_and_identities(config, rng, np_rng, fake)
    n_truth_rows = write_generation_truth(config, customers)
    consent_by_customer, n_consents = generate_consent_preferences(
        config, customers, rng
    )
    n_subscriptions = generate_subscriptions(config, customers, rng)
    orders_by_customer, n_orders, n_items = generate_orders(
        config, customers, products, rng, np_rng
    )
    n_campaign_exposures = generate_campaign_exposures(
        config,
        customers,
        campaigns,
        consent_by_customer,
        orders_by_customer,
        rng,
        np_rng,
    )
    n_tickets = generate_support_tickets(
        config, customers, orders_by_customer, rng, np_rng
    )
    n_sessions, n_logical_events, n_event_rows = generate_sessions_and_events(
        config, customers, products, orders_by_customer, rng, np_rng
    )

    elapsed = time.perf_counter() - start

    counts = {
        "customers": len(customers),
        "identities": n_identities,
        "products": len(products),
        "campaigns": len(campaigns),
        "campaign_exposures": n_campaign_exposures,
        "subscriptions": n_subscriptions,
        "consent_preferences": n_consents,
        "orders": n_orders,
        "order_items": n_items,
        "support_tickets": n_tickets,
        "sessions": n_sessions,
        "events_raw_rows": n_event_rows,
        "customer_generation_truth": n_truth_rows,
    }

    manifest = {
        "seed": config.seed,
        "generated_at": NOW_UTC.isoformat(),
        "elapsed_seconds": round(elapsed, 3),
        "configuration": {
            "customers": config.customers,
            "products": config.products,
            "campaigns": config.campaigns,
            "avg_orders": config.avg_orders,
            "avg_browsing_sessions": config.avg_browsing_sessions,
            "duplicate_event_rate": config.duplicate_event_rate,
            "late_event_rate": config.late_event_rate,
            "null_profile_rate": config.null_profile_rate,
            "output_format": config.output_format,
        },
        "row_counts": counts,
        "derived": {
            "rows_per_second": round(sum(counts.values()) / max(elapsed, 0.001), 2),
            "logical_event_ids_generated": n_logical_events,
            "raw_event_rows_written": n_event_rows,
        },
    }

    with (config.output_dir / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
