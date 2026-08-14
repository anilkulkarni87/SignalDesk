# Incremental Customer 360 Design

## Why the obvious implementation is wrong

A next-day Customer 360 can change without receiving a new row.

Example:

```text
2026-08-13:
orders_60d = 3

2026-08-14:
orders_60d = 2
```

An older order crossed the 60-day cutoff.

Therefore:

```text
affected customers =
    customers with changed source data
    UNION
    customers with facts crossing semantic time-window boundaries
```

## Volatile recency fields

The first Customer 360 materialized:

- `as_of_ts`
- `days_since_last_seen`
- `days_since_purchase`
- `days_since_last_support_case`
- `days_since_last_campaign`

If those values are materialized in feature marts, advancing one day makes nearly every customer stale.

The incremental-aware design instead materializes absolute timestamps:

- `last_seen_at`
- `last_purchase_at`
- `last_support_case_at`
- `last_campaign_at`

and calculates relative day counts in the final `customer_360` view.

This is not just a performance optimization. It separates:

```text
durable customer fact
from
query-time interpretation relative to as_of
```

## Boundary detection

Customers are added to the affected set when facts cross any window used by a feature:

- orders: 30d, 60d, 90d, 120d
- sessions: 30d, 60d, 90d, 120d
- events: 60d
- support tickets: 90d
- campaign exposures: 90d
- subscription cancellations: 90d

This intentionally over-selects slightly rather than risk a false negative.

## Benchmark contract

The benchmark compares two copies of the same staged baseline database.

Both receive the same delta.

### Incremental copy

```text
append delta
→ detect affected customers
→ recompute feature marts only for affected customers
→ replace those customer rows in materialized marts
→ expose customer_360 view
```

### Full-reference copy

```text
append delta
→ recompute every feature mart
→ expose customer_360 view
```

Then:

```text
incremental customer_360
EXCEPT
full customer_360
```

and the reverse must both return zero rows.

Exact reconciliation is mandatory. A faster pipeline that produces different semantics fails.

## What the benchmark does not measure

This benchmark starts from already-materialized staging tables.

It measures semantic-layer recomputation, not:

- raw Parquet ingestion,
- network transfer,
- upstream CDC extraction,
- warehouse scheduling overhead.

Keep that distinction explicit when reporting the benchmark.

## Decision rule

Do not keep incremental complexity merely because it works.

Compare:

- affected-customer percentage,
- full feature recompute time,
- incremental detection + recompute time,
- speedup,
- exact reconciliation.

If the speedup is small and a full refresh already completes comfortably inside the required SLA, prefer the simpler full refresh.
