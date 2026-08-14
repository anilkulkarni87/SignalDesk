#!/usr/bin/env python3
"""Generate a deterministic next-day staged delta for incremental benchmarking."""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
from datetime import datetime, timedelta
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--database", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--changed-customer-pct", type=float, default=0.02)
    p.add_argument("--advance-hours", type=int, default=24)
    p.add_argument("--seed", type=int, default=43)
    return p.parse_args()


def fmt(dt):
    return dt.isoformat()


def max_suffix(con, table, field):
    value = con.execute(
        f"""
        SELECT COALESCE(MAX(
            TRY_CAST(regexp_extract({field}, '([0-9]+)$', 1) AS BIGINT)
        ), 0)
        FROM {table}
        """
    ).fetchone()[0]
    return int(value or 0)


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def main():
    args = parse_args()
    try:
        import duckdb
    except ImportError as exc:
        raise SystemExit("Install DuckDB with: pip install duckdb") from exc

    rng = random.Random(args.seed)
    con = duckdb.connect(str(args.database), read_only=True)

    old_as_of = con.execute("SELECT as_of_ts FROM runtime_context").fetchone()[0]
    new_as_of = old_as_of + timedelta(hours=args.advance_hours)

    customer_ids = [r[0] for r in con.execute(
        "SELECT customer_id FROM stg_customers ORDER BY customer_id"
    ).fetchall()]
    n_changed = max(1, round(len(customer_ids) * args.changed_customer_pct))
    changed = sorted(rng.sample(customer_ids, n_changed))

    products = [r[0] for r in con.execute(
        "SELECT product_id FROM stg_products ORDER BY product_id"
    ).fetchall()]
    campaign_pairs = con.execute(
        """
        SELECT campaign_id, channel
        FROM stg_campaign_exposures
        GROUP BY campaign_id, channel
        ORDER BY campaign_id, channel
        """
    ).fetchall()

    consent = {
        r[0]: {"EMAIL": bool(r[1]), "SMS": bool(r[2]), "PUSH": bool(r[3])}
        for r in con.execute(
            """
            SELECT customer_id, email_opted_in, sms_opted_in, push_opted_in
            FROM int_customer_consent_features
            """
        ).fetchall()
    }

    next_ids = {
        "session": max_suffix(con, "stg_sessions", "session_id") + 1,
        "event": max_suffix(con, "stg_events", "event_id") + 1,
        "order": max_suffix(con, "stg_orders", "order_id") + 1,
        "item": max_suffix(con, "stg_order_items", "order_item_id") + 1,
        "ticket": max_suffix(con, "stg_support_tickets", "ticket_id") + 1,
        "exposure": max_suffix(con, "stg_campaign_exposures", "exposure_id") + 1,
        "subscription": max_suffix(con, "stg_subscriptions", "subscription_id") + 1,
        "consent": max_suffix(con, "stg_consent_preferences", "consent_id") + 1,
    }

    sessions, events, orders, items = [], [], [], []
    tickets, exposures, subscriptions, consents = [], [], [], []

    campaign_by_channel = {"EMAIL": [], "SMS": [], "PUSH": []}
    for campaign_id, channel in campaign_pairs:
        if channel in campaign_by_channel:
            campaign_by_channel[channel].append(campaign_id)

    for customer_id in changed:
        seconds = rng.randint(60, max(61, int((new_as_of - old_as_of).total_seconds()) - 3600))
        session_start = old_as_of + timedelta(seconds=seconds)
        session_end = min(new_as_of, session_start + timedelta(minutes=rng.randint(4, 35)))
        session_id = f"S{next_ids['session']:010d}"
        next_ids["session"] += 1

        sessions.append({
            "session_id": session_id,
            "observed_customer_id": customer_id,
            "resolved_customer_id": customer_id,
            "identity_id": "",
            "session_started_at": fmt(session_start),
            "session_ended_at": fmt(session_end),
            "channel": rng.choice(["web", "mobile_web", "app"]),
        })

        product_id = rng.choice(products)
        for event_type, offset in [("product_view", 30), ("add_to_cart", 150)]:
            event_ts = min(new_as_of, session_start + timedelta(seconds=offset))
            events.append({
                "event_id": f"E{next_ids['event']:012d}",
                "event_type": event_type,
                "event_timestamp": fmt(event_ts),
                "received_at": fmt(min(
                    new_as_of,
                    event_ts + timedelta(seconds=rng.randint(1, 15))
                )),
                "observed_customer_id": customer_id,
                "identity_id": "",
                "session_id": session_id,
                "product_id": product_id,
                "order_id": "",
                "resolved_customer_id": customer_id,
            })
            next_ids["event"] += 1

        if rng.random() < 0.35:
            order_id = f"O{next_ids['order']:09d}"
            item_id = f"OI{next_ids['item']:010d}"
            next_ids["order"] += 1
            next_ids["item"] += 1
            order_ts = min(new_as_of, session_start + timedelta(minutes=rng.randint(5, 45)))
            unit_price = round(rng.uniform(20, 200), 2)
            discount = round(unit_price * (0.10 if rng.random() < 0.35 else 0), 2)
            line_total = round(unit_price - discount, 2)
            total = round(line_total * 1.08, 2)

            orders.append({
                "order_id": order_id,
                "customer_id": customer_id,
                "order_timestamp": fmt(order_ts),
                "status": "COMPLETED",
                "channel": rng.choice(["web", "app"]),
                "total_amount": total,
                "discount_amount": discount,
            })
            items.append({
                "order_item_id": item_id,
                "order_id": order_id,
                "product_id": product_id,
                "quantity": 1,
                "unit_price": unit_price,
                "line_discount": discount,
                "line_total": line_total,
            })

        if rng.random() < 0.15:
            opened = min(new_as_of, session_start + timedelta(minutes=rng.randint(10, 120)))
            tickets.append({
                "ticket_id": f"T{next_ids['ticket']:08d}",
                "customer_id": customer_id,
                "order_id": "",
                "opened_at": fmt(opened),
                "closed_at": "",
                "status": "OPEN",
                "category": rng.choice(["shipping_delay", "damaged_item", "refund_request"]),
                "priority": rng.choice(["MEDIUM", "HIGH"]),
                "sentiment": rng.choice(["NEGATIVE", "NEUTRAL"]),
                "csat_score": 2,
            })
            next_ids["ticket"] += 1

        if rng.random() < 0.30:
            allowed = [
                ch for ch, ok in consent.get(customer_id, {}).items()
                if ok and campaign_by_channel.get(ch)
            ]
            if allowed:
                channel = rng.choice(allowed)
                sent_at = min(new_as_of, session_start + timedelta(minutes=rng.randint(1, 90)))
                opened = rng.random() < 0.45
                clicked = opened and rng.random() < 0.25
                exposures.append({
                    "exposure_id": f"EXP{next_ids['exposure']:010d}",
                    "customer_id": customer_id,
                    "campaign_id": rng.choice(campaign_by_channel[channel]),
                    "channel": channel,
                    "sent_at": fmt(sent_at),
                    "delivery_status": "DELIVERED",
                    "opened_at": fmt(min(new_as_of, sent_at + timedelta(minutes=5))) if opened else "",
                    "clicked_at": fmt(min(new_as_of, sent_at + timedelta(minutes=12))) if clicked else "",
                    "converted_order_id": "",
                })
                next_ids["exposure"] += 1

        if rng.random() < 0.05:
            started = session_start
            subscriptions.append({
                "subscription_id": f"SUB{next_ids['subscription']:09d}",
                "customer_id": customer_id,
                "subscription_type": rng.choice(["NEWSLETTER", "LOYALTY_PROGRAM", "REPLENISHMENT"]),
                "status": "ACTIVE",
                "started_at": fmt(started),
                "ended_at": "",
                "renewal_at": fmt(new_as_of + timedelta(days=rng.randint(20, 90))),
            })
            next_ids["subscription"] += 1

        if rng.random() < 0.08:
            channel = rng.choice(["EMAIL", "SMS", "PUSH"])
            current = consent.get(customer_id, {}).get(channel, False)
            consents.append({
                "consent_id": f"CN{next_ids['consent']:09d}",
                "customer_id": customer_id,
                "channel": channel,
                "status": "OPTED_OUT" if current else "OPTED_IN",
                "updated_at": fmt(session_start),
                "source": "ACCOUNT_SETTINGS",
            })
            next_ids["consent"] += 1

    files = {
        "sessions.csv": (
            ["session_id", "observed_customer_id", "resolved_customer_id", "identity_id",
             "session_started_at", "session_ended_at", "channel"], sessions
        ),
        "events.csv": (
            ["event_id", "event_type", "event_timestamp", "received_at",
             "observed_customer_id", "identity_id", "session_id", "product_id",
             "order_id", "resolved_customer_id"], events
        ),
        "orders.csv": (
            ["order_id", "customer_id", "order_timestamp", "status", "channel",
             "total_amount", "discount_amount"], orders
        ),
        "order_items.csv": (
            ["order_item_id", "order_id", "product_id", "quantity", "unit_price",
             "line_discount", "line_total"], items
        ),
        "support_tickets.csv": (
            ["ticket_id", "customer_id", "order_id", "opened_at", "closed_at",
             "status", "category", "priority", "sentiment", "csat_score"], tickets
        ),
        "campaign_exposures.csv": (
            ["exposure_id", "customer_id", "campaign_id", "channel", "sent_at",
             "delivery_status", "opened_at", "clicked_at", "converted_order_id"], exposures
        ),
        "subscriptions.csv": (
            ["subscription_id", "customer_id", "subscription_type", "status",
             "started_at", "ended_at", "renewal_at"], subscriptions
        ),
        "consent_preferences.csv": (
            ["consent_id", "customer_id", "channel", "status", "updated_at", "source"], consents
        ),
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, (fields, rows) in files.items():
        write_csv(args.output_dir / name, fields, rows)

    write_csv(
        args.output_dir / "changed_customers.csv",
        ["customer_id"],
        [{"customer_id": c} for c in changed],
    )

    manifest = {
        "base_as_of_ts": fmt(old_as_of),
        "next_as_of_ts": fmt(new_as_of),
        "changed_customer_pct": args.changed_customer_pct,
        "changed_customers": len(changed),
        "row_counts": {name.replace(".csv", ""): len(rows) for name, (_, rows) in files.items()},
        "seed": args.seed,
    }
    (args.output_dir / "delta_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
