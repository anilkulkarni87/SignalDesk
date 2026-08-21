#!/usr/bin/env python3
"""Build an incremental-ready NovaCart Customer 360 using DuckDB."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

TABLES = [
    "customers",
    "identities",
    "sessions",
    "events",
    "orders",
    "order_items",
    "products",
    "support_tickets",
    "campaign_exposures",
    "subscriptions",
    "consent_preferences",
]
SEMANTIC_TIMEZONE = "America/Los_Angeles"


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--input-dir", type=Path, required=True)
    p.add_argument("--sql-dir", type=Path, default=Path(__file__).parent / "sql")
    p.add_argument("--database", type=Path, default=Path("data/warehouse/signaldesk.duckdb"))
    p.add_argument("--output", type=Path, default=Path("data/warehouse/customer_360.parquet"))
    return p.parse_args()


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def source_expression(path: Path) -> str:
    p = sql_literal(path.resolve().as_posix())
    if path.suffix == ".parquet":
        return f"read_parquet({p})"
    if path.suffix == ".csv":
        return f"read_csv_auto({p}, header=true)"
    raise ValueError(path)


def find_source(input_dir: Path, table: str) -> Path:
    for suffix in (".parquet", ".csv"):
        candidate = input_dir / f"{table}{suffix}"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Missing {table}.parquet or {table}.csv in {input_dir}")


def main():
    args = parse_args()
    try:
        import duckdb
    except ImportError as exc:
        raise SystemExit("Install DuckDB with: pip install duckdb") from exc

    manifest = json.loads((args.input_dir / "manifest.json").read_text(encoding="utf-8"))
    as_of_ts = manifest["generated_at"]

    args.database.parent.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(args.database))
    con.execute("SET TimeZone = ?", [SEMANTIC_TIMEZONE])

    for table in TABLES:
        path = find_source(args.input_dir, table)
        con.execute(
            f"CREATE OR REPLACE VIEW raw_{table} AS "
            f"SELECT * FROM {source_expression(path)}"
        )

    con.execute(
        "CREATE OR REPLACE TABLE runtime_context AS "
        "SELECT CAST(? AS TIMESTAMPTZ) AS as_of_ts",
        [as_of_ts],
    )

    started = time.perf_counter()
    con.execute((args.sql_dir / "staging.sql").read_text(encoding="utf-8"))
    con.execute("CREATE OR REPLACE VIEW feature_customers AS SELECT * FROM stg_customers")
    con.execute((args.sql_dir / "intermediate.sql").read_text(encoding="utf-8"))
    con.execute((args.sql_dir / "customer_360.sql").read_text(encoding="utf-8"))
    elapsed = time.perf_counter() - started

    rows = con.execute("SELECT COUNT(*) FROM customer_360").fetchone()[0]
    source_rows = con.execute("SELECT COUNT(*) FROM stg_customers").fetchone()[0]

    out = sql_literal(args.output.resolve().as_posix())
    con.execute(f"COPY customer_360 TO {out} (FORMAT PARQUET, COMPRESSION ZSTD)")

    metrics = {
        "as_of_ts": as_of_ts,
        "customer_360_rows": rows,
        "source_customer_rows": source_rows,
        "transform_seconds": round(elapsed, 3),
        "customers_per_second": round(rows / max(elapsed, 0.001), 2),
        "database": str(args.database),
        "output": str(args.output),
        "incremental_ready": True,
    }
    args.output.with_name("customer_360_build_metrics.json").write_text(
        json.dumps(metrics, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
