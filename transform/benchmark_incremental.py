#!/usr/bin/env python3
"""
Benchmark incremental Customer 360 against a fresh full semantic recompute.

This benchmark intentionally starts from an already-built staged DuckDB database.
It measures semantic recomputation, not raw Parquet ingestion.

Workflow:
1. Copy baseline database twice.
2. Append the exact same next-day delta to both copies.
3. Incremental copy:
   - find data-changed + time-boundary-affected customers
   - recompute only those feature marts
4. Full copy:
   - recompute all feature marts
5. Compare every customer_360 row/column with EXCEPT in both directions.
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path


DELTA_TABLES = {
    "sessions": "stg_sessions",
    "events": "stg_events",
    "orders": "stg_orders",
    "order_items": "stg_order_items",
    "support_tickets": "stg_support_tickets",
    "campaign_exposures": "stg_campaign_exposures",
    "subscriptions": "stg_subscriptions",
    "consent_preferences": "stg_consent_preferences",
}

FEATURE_TABLES = [
    "int_customer_identity_features",
    "int_customer_preferred_category",
    "int_customer_purchase_features",
    "int_customer_channel_affinity",
    "int_customer_engagement_features",
    "int_customer_support_features",
    "int_customer_campaign_features",
    "int_customer_subscription_features",
    "int_customer_consent_features",
]


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--baseline-database", type=Path, required=True)
    p.add_argument("--delta-dir", type=Path, required=True)
    p.add_argument("--sql-dir", type=Path, default=Path(__file__).parent / "sql")
    p.add_argument("--work-dir", type=Path, default=Path("data/warehouse/incremental_benchmark"))
    p.add_argument("--report", type=Path, default=None)
    return p.parse_args()


def q(path: Path) -> str:
    return "'" + path.resolve().as_posix().replace("'", "''") + "'"


def load_manifest(delta_dir):
    return json.loads((delta_dir / "delta_manifest.json").read_text(encoding="utf-8"))


def apply_delta(con, delta_dir, manifest):
    started = time.perf_counter()
    for logical, target in DELTA_TABLES.items():
        count = manifest["row_counts"].get(logical, 0)
        if not count:
            continue
        path = delta_dir / f"{logical}.csv"
        con.execute(
            f"INSERT INTO {target} BY NAME "
            f"SELECT * FROM read_csv_auto({q(path)}, header=true, nullstr='')"
        )
    return time.perf_counter() - started


def create_affected(con, delta_dir, old_ts, new_ts):
    changed_path = delta_dir / "changed_customers.csv"

    sql = f"""
    CREATE OR REPLACE TABLE affected_customer_ids AS
    WITH changed AS (
        SELECT customer_id
        FROM read_csv_auto({q(changed_path)}, header=true)
    ),
    boundaries AS (
        SELECT customer_id
        FROM stg_orders
        WHERE
            (order_timestamp > CAST(? AS TIMESTAMPTZ) - INTERVAL '30 days'
             AND order_timestamp <= CAST(? AS TIMESTAMPTZ) - INTERVAL '30 days')
         OR (order_timestamp > CAST(? AS TIMESTAMPTZ) - INTERVAL '60 days'
             AND order_timestamp <= CAST(? AS TIMESTAMPTZ) - INTERVAL '60 days')
         OR (order_timestamp > CAST(? AS TIMESTAMPTZ) - INTERVAL '90 days'
             AND order_timestamp <= CAST(? AS TIMESTAMPTZ) - INTERVAL '90 days')
         OR (order_timestamp > CAST(? AS TIMESTAMPTZ) - INTERVAL '120 days'
             AND order_timestamp <= CAST(? AS TIMESTAMPTZ) - INTERVAL '120 days')

        UNION

        SELECT resolved_customer_id AS customer_id
        FROM stg_sessions
        WHERE resolved_customer_id IS NOT NULL
          AND (
            (session_started_at > CAST(? AS TIMESTAMPTZ) - INTERVAL '30 days'
             AND session_started_at <= CAST(? AS TIMESTAMPTZ) - INTERVAL '30 days')
         OR (session_started_at > CAST(? AS TIMESTAMPTZ) - INTERVAL '60 days'
             AND session_started_at <= CAST(? AS TIMESTAMPTZ) - INTERVAL '60 days')
         OR (session_started_at > CAST(? AS TIMESTAMPTZ) - INTERVAL '90 days'
             AND session_started_at <= CAST(? AS TIMESTAMPTZ) - INTERVAL '90 days')
         OR (session_started_at > CAST(? AS TIMESTAMPTZ) - INTERVAL '120 days'
             AND session_started_at <= CAST(? AS TIMESTAMPTZ) - INTERVAL '120 days')
          )

        UNION

        SELECT resolved_customer_id AS customer_id
        FROM stg_events
        WHERE resolved_customer_id IS NOT NULL
          AND event_timestamp > CAST(? AS TIMESTAMPTZ) - INTERVAL '60 days'
          AND event_timestamp <= CAST(? AS TIMESTAMPTZ) - INTERVAL '60 days'

        UNION

        SELECT customer_id
        FROM stg_support_tickets
        WHERE opened_at > CAST(? AS TIMESTAMPTZ) - INTERVAL '90 days'
          AND opened_at <= CAST(? AS TIMESTAMPTZ) - INTERVAL '90 days'

        UNION

        SELECT customer_id
        FROM stg_campaign_exposures
        WHERE sent_at > CAST(? AS TIMESTAMPTZ) - INTERVAL '90 days'
          AND sent_at <= CAST(? AS TIMESTAMPTZ) - INTERVAL '90 days'

        UNION

        SELECT customer_id
        FROM stg_subscriptions
        WHERE status = 'CANCELED'
          AND ended_at > CAST(? AS TIMESTAMPTZ) - INTERVAL '90 days'
          AND ended_at <= CAST(? AS TIMESTAMPTZ) - INTERVAL '90 days'
    )
    SELECT customer_id FROM changed
    UNION
    SELECT customer_id FROM boundaries
    WHERE customer_id IS NOT NULL
    """

    # Each old/new pair is repeated for each cutoff predicate.
    params = []
    for _ in range(4):
        params.extend([old_ts, new_ts])
    for _ in range(4):
        params.extend([old_ts, new_ts])
    params.extend([old_ts, new_ts])  # events
    params.extend([old_ts, new_ts])  # support
    params.extend([old_ts, new_ts])  # campaign
    params.extend([old_ts, new_ts])  # subscriptions

    started = time.perf_counter()
    con.execute(sql, params)
    elapsed = time.perf_counter() - started
    count = con.execute("SELECT COUNT(*) FROM affected_customer_ids").fetchone()[0]
    changed = con.execute(
        f"SELECT COUNT(*) FROM read_csv_auto({q(changed_path)}, header=true)"
    ).fetchone()[0]
    return elapsed, count, changed


def patch_sql(full_sql: str) -> str:
    patched = full_sql.replace("int_customer_", "patch_int_customer_")
    patched = patched.replace(
        "CREATE OR REPLACE TABLE patch_int_customer_",
        "CREATE OR REPLACE TEMP TABLE patch_int_customer_",
    )
    return patched


def incremental_transform(con, sql_dir, new_ts):
    con.execute(
        "UPDATE runtime_context SET as_of_ts = CAST(? AS TIMESTAMPTZ)",
        [new_ts],
    )
    con.execute(
        """
        CREATE OR REPLACE VIEW feature_customers AS
        SELECT c.*
        FROM stg_customers c
        JOIN affected_customer_ids a USING (customer_id)
        """
    )

    full_sql = (sql_dir / "intermediate.sql").read_text(encoding="utf-8")
    psql = patch_sql(full_sql)

    started = time.perf_counter()
    con.execute(psql)

    for target in FEATURE_TABLES:
        patch = target.replace("int_customer_", "patch_int_customer_")
        con.execute(
            f"DELETE FROM {target} "
            "WHERE customer_id IN (SELECT customer_id FROM affected_customer_ids)"
        )
        con.execute(f"INSERT INTO {target} SELECT * FROM {patch}")

    con.execute("CREATE OR REPLACE VIEW feature_customers AS SELECT * FROM stg_customers")
    con.execute((sql_dir / "customer_360.sql").read_text(encoding="utf-8"))
    return time.perf_counter() - started


def full_transform(con, sql_dir, new_ts):
    con.execute(
        "UPDATE runtime_context SET as_of_ts = CAST(? AS TIMESTAMPTZ)",
        [new_ts],
    )
    con.execute("DROP VIEW IF EXISTS customer_360")
    con.execute("CREATE OR REPLACE VIEW feature_customers AS SELECT * FROM stg_customers")

    started = time.perf_counter()
    con.execute((sql_dir / "intermediate.sql").read_text(encoding="utf-8"))
    con.execute((sql_dir / "customer_360.sql").read_text(encoding="utf-8"))
    return time.perf_counter() - started


def reconcile(incremental_db, full_db):
    import duckdb

    con = duckdb.connect(str(incremental_db), read_only=True)
    con.execute(f"ATTACH {q(full_db)} AS fullref (READ_ONLY)")

    inc_minus_full = con.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT * FROM customer_360
            EXCEPT
            SELECT * FROM fullref.customer_360
        )
        """
    ).fetchone()[0]

    full_minus_inc = con.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT * FROM fullref.customer_360
            EXCEPT
            SELECT * FROM customer_360
        )
        """
    ).fetchone()[0]

    inc_rows = con.execute("SELECT COUNT(*) FROM customer_360").fetchone()[0]
    full_rows = con.execute("SELECT COUNT(*) FROM fullref.customer_360").fetchone()[0]

    return {
        "incremental_rows": inc_rows,
        "full_rows": full_rows,
        "incremental_minus_full_rows": inc_minus_full,
        "full_minus_incremental_rows": full_minus_inc,
        "exact_match": inc_minus_full == 0 and full_minus_inc == 0 and inc_rows == full_rows,
    }


def main():
    args = parse_args()
    try:
        import duckdb
    except ImportError as exc:
        raise SystemExit("Install DuckDB with: pip install duckdb") from exc

    args.work_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.report or (args.work_dir / "incremental_benchmark_report.json")

    manifest = load_manifest(args.delta_dir)
    old_ts = manifest["base_as_of_ts"]
    new_ts = manifest["next_as_of_ts"]

    incremental_db = args.work_dir / "incremental.duckdb"
    full_db = args.work_dir / "full_reference.duckdb"

    for path in (incremental_db, full_db):
        if path.exists():
            path.unlink()
        shutil.copy2(args.baseline_database, path)

    inc = duckdb.connect(str(incremental_db))
    baseline_ts = str(inc.execute("SELECT as_of_ts FROM runtime_context").fetchone()[0])
    if baseline_ts.replace(" ", "T")[:19] != old_ts.replace(" ", "T")[:19]:
        raise RuntimeError(
            f"Baseline DB as_of_ts {baseline_ts} does not match delta base {old_ts}"
        )

    inc_apply = apply_delta(inc, args.delta_dir, manifest)
    detect_seconds, affected, changed = create_affected(inc, args.delta_dir, old_ts, new_ts)
    inc_transform = incremental_transform(inc, args.sql_dir, new_ts)
    inc.close()

    full = duckdb.connect(str(full_db))
    full_apply = apply_delta(full, args.delta_dir, manifest)
    full_transform_seconds = full_transform(full, args.sql_dir, new_ts)
    full.close()

    reconciliation = reconcile(incremental_db, full_db)

    customer_count = reconciliation["full_rows"]
    speedup = (
        full_transform_seconds / inc_transform
        if inc_transform > 0 else None
    )

    report = {
        "base_as_of_ts": old_ts,
        "next_as_of_ts": new_ts,
        "baseline_database": str(args.baseline_database),
        "changed_customers": changed,
        "affected_customers": affected,
        "affected_customer_pct": round(100 * affected / customer_count, 3)
            if customer_count else 0,
        "incremental": {
            "delta_apply_seconds": round(inc_apply, 4),
            "affected_detection_seconds": round(detect_seconds, 4),
            "feature_transform_seconds": round(inc_transform, 4),
            "total_semantic_seconds": round(detect_seconds + inc_transform, 4),
        },
        "full_reference": {
            "delta_apply_seconds": round(full_apply, 4),
            "feature_transform_seconds": round(full_transform_seconds, 4),
        },
        "feature_transform_speedup_x": round(speedup, 3) if speedup else None,
        "reconciliation": reconciliation,
        "decision_note": (
            "Use the measured speedup and affected-customer percentage to decide "
            "whether incremental complexity is justified. Exact reconciliation is mandatory."
        ),
    }

    report["passed"] = reconciliation["exact_match"]

    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
