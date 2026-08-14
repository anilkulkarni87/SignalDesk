# Customer 360 Contract — Commit 03

## Purpose

Commit 03 converts the synthetic NovaCart CDP from raw event/domain tables into a deterministic semantic layer that SignalDesk can query reliably.

The target flow is:

```text
raw Parquet / CSV
        ↓
staging
        ↓
intermediate feature marts
        ↓
customer_360
```

The semantic layer exists to calculate customer facts deterministically before any LLM is introduced.

## Grain

`customer_360` has exactly **one row per resolved NovaCart customer**.

Primary key:

```text
customer_id
```

The expected row count is equal to the row count of `customers`.

## As-of semantics

Every build has one explicit `as_of_ts`.

For generated data, `as_of_ts` comes from `manifest.json -> generated_at`.

All 30/60/90-day windows are calculated relative to that timestamp rather than the machine's wall clock. This makes the transformation reproducible even when the same dataset is rebuilt later.

Window convention:

```text
recent 30d       (as_of - 30d, as_of]
recent 60d       (as_of - 60d, as_of]
recent 90d       (as_of - 90d, as_of]
prior 60d        (as_of - 120d, as_of - 60d]
```

## Identity resolution

Raw sessions and events may have a blank `customer_id` before an anonymous cookie identity is resolved.

Staging preserves both concepts:

```text
observed_customer_id
resolved_customer_id
```

Resolution rule:

```text
resolved_customer_id =
    observed customer_id
    else identities.customer_id through identity_id
```

Customer-level features aggregate on `resolved_customer_id`.

We do not rewrite the raw record or claim that the source knew the customer at event time.

## Revenue and order semantics

A successful purchase is an order whose status is:

```text
COMPLETED
SHIPPED
```

`CANCELED` and `REFUNDED` orders do not contribute to successful-order counts or revenue.

They remain available for refund/cancellation metrics.

`lifetime_value` in Commit 03 therefore means:

> Sum of `total_amount` for successful orders in the synthetic dataset.

It is not a predictive customer-lifetime-value model.

## PII boundary

The Customer 360 intentionally excludes raw:

- email address
- phone number
- date of birth
- postal address
- identity values

SignalDesk later needs customer evidence, not unnecessary PII in every LLM context.

---

# V1 Feature Contract

## Core / identity

| Feature | Type | Definition |
|---|---|---|
| `customer_id` | string | Resolved customer primary key |
| `as_of_ts` | timestamp | Dataset build timestamp |
| `profile_created_at` | timestamp | `customers.created_at` |
| `first_seen_at` | timestamp | Earliest first-seen timestamp across resolved identities |
| `last_seen_at` | timestamp | Latest customer-originated activity across identity/session/event/order/support evidence |
| `days_since_last_seen` | integer | Days from `last_seen_at` to `as_of_ts` |
| `resolved_identity_count` | integer | Number of identities attached to customer |
| `customer_status` | string | Current customer profile status |
| `loyalty_tier` | string | Current loyalty tier |
| `country` | string | Customer country |
| `timezone` | string | Customer timezone |

## Purchase features

| Feature | Type | Definition |
|---|---|---|
| `lifetime_orders` | integer | Successful orders over all history |
| `lifetime_value` | decimal | Successful-order revenue over all history |
| `orders_30d` | integer | Successful orders in recent 30d |
| `orders_60d` | integer | Successful orders in recent 60d |
| `orders_90d` | integer | Successful orders in recent 90d |
| `orders_prior_60d` | integer | Successful orders in prior comparison window |
| `revenue_60d` | decimal | Successful-order revenue in recent 60d |
| `revenue_prior_60d` | decimal | Successful-order revenue in prior comparison window |
| `days_since_purchase` | integer nullable | Days since most recent successful order |
| `avg_order_value_lifetime` | decimal nullable | `lifetime_value / lifetime_orders` |
| `refund_rate_90d` | decimal | Refunded orders / all orders in recent 90d |
| `purchase_change_pct` | decimal nullable | `(orders_60d - orders_prior_60d) / orders_prior_60d` |
| `preferred_category` | string nullable | Highest successful-order item spend by product category; deterministic lexical tie-break |
| `purchase_decline_flag` | boolean | Prior-window orders >= 2 and recent 60d orders < prior 60d orders |

## Behavioral engagement

| Feature | Type | Definition |
|---|---|---|
| `sessions_30d` | integer | Resolved sessions in recent 30d |
| `sessions_60d` | integer | Resolved sessions in recent 60d |
| `sessions_90d` | integer | Resolved sessions in recent 90d |
| `sessions_prior_60d` | integer | Resolved sessions in prior comparison window |
| `session_change_pct` | decimal nullable | `(sessions_60d - sessions_prior_60d) / sessions_prior_60d` |
| `product_views_60d` | integer | Deduplicated `product_view` events in recent 60d |
| `add_to_cart_60d` | integer | Deduplicated `add_to_cart` events in recent 60d |
| `checkout_starts_60d` | integer | Deduplicated `checkout_started` events in recent 60d |
| `channel_affinity` | string nullable | Most frequent session channel in recent 90d; lexical tie-break |
| `engagement_decline_flag` | boolean | Prior-window sessions >= 2 and recent 60d sessions < prior 60d sessions |

## Support

| Feature | Type | Definition |
|---|---|---|
| `support_cases_lifetime` | integer | All support cases |
| `support_cases_90d` | integer | Cases opened in recent 90d |
| `open_support_cases` | integer | Current `OPEN` or `PENDING` cases |
| `negative_support_cases_90d` | integer | Recent cases with `NEGATIVE` sentiment |
| `high_priority_support_cases_90d` | integer | Recent `HIGH` or `URGENT` cases |
| `days_since_last_support_case` | integer nullable | Days since latest support case |
| `avg_csat_90d` | decimal nullable | Average non-null CSAT for recent cases |
| `support_attention_flag` | boolean | Any open/pending case OR at least two negative recent cases |

## Campaign engagement

| Feature | Type | Definition |
|---|---|---|
| `campaigns_delivered_90d` | integer | Delivered campaign exposures in recent 90d |
| `email_delivered_90d` | integer | Delivered EMAIL exposures in recent 90d |
| `email_opens_90d` | integer | Email exposures with `opened_at` in recent 90d |
| `email_clicks_90d` | integer | Email exposures with `clicked_at` in recent 90d |
| `email_open_rate_90d` | decimal | Email opens / email delivered; 0 when no delivery |
| `email_click_rate_90d` | decimal | Email clicks / email delivered; 0 when no delivery |
| `email_engagement` | string | `CLICKED`, `OPENED`, `DELIVERED_NO_ENGAGEMENT`, or `NO_RECENT_EMAIL` |
| `days_since_last_campaign` | integer nullable | Days since latest campaign send |

## Subscription / consent

| Feature | Type | Definition |
|---|---|---|
| `active_subscription_count` | integer | Current active subscriptions |
| `recent_subscription_cancellation_flag` | boolean | Any subscription canceled in recent 90d |
| `email_opted_in` | boolean | Latest EMAIL consent state |
| `sms_opted_in` | boolean | Latest SMS consent state |
| `push_opted_in` | boolean | Latest PUSH consent state |

---

# Deliberately excluded from V1

## `churn_signal`

The roadmap originally lists `churn_signal`, but Commit 01 established that NovaCart already has an upstream at-risk model.

Commit 03 should explain risk, not silently create a replacement prediction model.

Instead we expose deterministic evidence:

```text
purchase_decline_flag
engagement_decline_flag
support_attention_flag
```

A future upstream risk score can be joined to Customer 360 as a separate source with clear provenance.

## Composite engagement score

We also avoid an arbitrary weighted `engagement_score` in V1.

Counts, rates, changes, and deterministic flags remain inspectable and easier to reconcile.

---

# Null semantics

Null should mean **unknown / not computable**, not zero.

Examples:

- no previous successful purchase → `days_since_purchase = NULL`
- zero prior-window orders → `purchase_change_pct = NULL`
- no CSAT observations → `avg_csat_90d = NULL`

Zero means the event was observed not to occur:

- no recent orders → `orders_60d = 0`
- no recent support cases → `support_cases_90d = 0`
- no email delivery → `email_open_rate_90d = 0`

---

# Definition of done for the semantic contract

A feature is not complete until it has:

1. a single grain,
2. a source-of-truth,
3. an explicit time window,
4. null semantics,
5. deterministic calculation logic,
6. at least one validation or reconciliation test.
