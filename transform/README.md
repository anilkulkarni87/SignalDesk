# Commit 03 — Incremental Customer 360 Benchmark

## 1. Replace the full-build files

Copy:

```text
transform/build_customer_360.py
transform/sql/intermediate.sql
transform/sql/customer_360.sql
```

from this bundle into the repository.

The staging SQL and 33-test validator remain compatible.

## 2. Rebuild the baseline database once

This migration changes feature-mart columns and makes `customer_360` a view.

```bash
rm -f data/warehouse/signaldesk.duckdb

python transform/build_customer_360.py \
  --input-dir data/generated/scale/000100000_customers \
  --database data/warehouse/signaldesk.duckdb \
  --output data/warehouse/customer_360.parquet

python transform/validate_customer_360.py \
  --database data/warehouse/signaldesk.duckdb
```

Require: `33/33` tests passing.

## 3. Generate a controlled next-day delta

Default: 2% of customers receive new staged activity.

```bash
python transform/generate_incremental_delta.py \
  --database data/warehouse/signaldesk.duckdb \
  --output-dir data/generated/incremental/day1 \
  --changed-customer-pct 0.02 \
  --advance-hours 24
```

## 4. Run incremental vs full-reference benchmark

The script copies the baseline database, so it does not mutate the baseline.

```bash
python transform/benchmark_incremental.py \
  --baseline-database data/warehouse/signaldesk.duckdb \
  --delta-dir data/generated/incremental/day1 \
  --sql-dir transform/sql \
  --work-dir data/warehouse/incremental_benchmark
```

The report is written to:

```text
data/warehouse/incremental_benchmark/incremental_benchmark_report.json
```

## Required result

```text
reconciliation.exact_match = true
```

Then evaluate whether:

```text
incremental detection + transform
```

is materially faster than:

```text
full feature-mart recompute
```

If not, keep full refresh.
