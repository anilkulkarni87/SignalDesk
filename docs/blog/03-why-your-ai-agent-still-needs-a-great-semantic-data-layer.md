# Why Your AI Agent Still Needs a Great Semantic Data Layer

After building the synthetic CDP for SignalDesk, I was finally close to the part of the project that looks like AI.

But before calling an LLM, I built another layer that looks much more familiar to a data engineer: a Customer 360.

That turned out to be exactly the point.

## The LLM should not calculate basic customer facts

Imagine asking an AI system:

> Why has customer C123's purchasing declined?

The raw CDP contains orders, sessions, events, support tickets, campaign exposures, subscriptions, identities, and consent records.

One approach would be to send a pile of raw rows to an LLM and ask it to figure everything out.

I do not want SignalDesk to work that way.

Questions such as these should already have deterministic answers:

- How many orders did the customer place in the last 60 days?
- How many did they place in the prior 60 days?
- What was their recent revenue?
- When was their last purchase?
- Do they have unresolved support cases?
- Has session activity declined?
- Are they opted in to email?

Those are data-engineering problems.

So Commit 03 became:

```text
raw
 ↓
staging
 ↓
domain feature marts
 ↓
customer_360
```

I used DuckDB for the analytical engine, SQL for the transformations, and Python for orchestration and validation.

## Define the meaning before writing the SQL

The most useful decision was to write the semantic contract first.

For every feature I had to define things such as:

- the customer grain,
- the as-of timestamp,
- the exact 30/60/90-day window,
- whether a refunded order counts as revenue,
- what null means,
- what zero means,
- how anonymous behavior becomes associated with a customer.

That last problem is especially important in a CDP.

A browsing session may begin anonymously and later become associated with a known identity.

Instead of rewriting the source history, the staging layer keeps both:

```text
observed_customer_id
resolved_customer_id
```

Customer 360 aggregates using the resolved identity while preserving what the source originally knew.

That gives the AI system a better fact base without pretending the raw data was cleaner than it really was.

## I deliberately did not build a churn score

The original roadmap included a `churn_signal`.

But earlier discovery established that NovaCart already has an upstream at-risk model.

Creating another churn score inside Customer 360 would duplicate that responsibility and hide business logic behind a new heuristic.

Instead, the semantic layer exposes evidence such as:

```text
purchase_decline_flag
engagement_decline_flag
support_attention_flag
```

Later, an LLM can reason about those facts.

It should not secretly manufacture them.

## The full refresh was already fast

At 100,000 customers, the full Customer 360 build produced exactly 100,000 rows.

It completed in:

**3.43 seconds**

or about:

**29,151 customers per second**

I added 33 validation tests covering grain, completeness, time-window consistency, bounded rates, decline definitions, support metrics, campaign metrics, and semantic invariants.

Result:

**33 / 33 passed**

That gave me a trustworthy baseline before optimization.

## Then I tested incremental processing

The obvious incremental strategy sounds simple:

> Recompute customers that received new rows.

For a time-windowed semantic layer, that is wrong.

Suppose an order is inside the 60-day window today.

Tomorrow, the same order may become 61 days old.

The customer changed semantically even though no new order arrived.

So the affected population is really:

```text
customers with new or changed data
+
customers whose existing facts crossed a time boundary
```

I generated next-day activity for 2,000 customers, or 2% of the population.

After accounting for 30/60/90/120-day boundary changes, the affected set became:

**23,645 customers**

or:

**23.645% of the population**

A 2% source-data change expanded into almost twelve times as many semantic changes.

That was the most interesting result of the experiment.

## A small modeling change made incremental processing cleaner

My first version materialized fields such as:

```text
days_since_purchase
days_since_last_seen
days_since_last_support_case
```

But those values change simply because time advances.

That would make many rows appear stale every day.

I changed the feature marts to store durable facts instead:

```text
last_purchase_at
last_seen_at
last_support_case_at
last_campaign_at
```

The final Customer 360 view calculates `days_since_*` relative to the current as-of timestamp.

That separates the durable fact from its time-relative interpretation.

It also makes the incremental model much more sensible.

## Incremental was faster, but that was not the final question

The incremental feature computation took:

**0.377 seconds**

The full feature recomputation took:

**0.957 seconds**

That is a:

**2.54x feature-computation speedup**

But incremental processing also required about:

**0.210 seconds**

to identify the affected customers.

So the practical semantic-layer comparison was closer to:

```text
incremental:
0.587 seconds

full:
0.957 seconds
```

or roughly:

**1.63x**

That is faster.

It is not automatically better.

## Correctness came before the speedup

I benchmarked incremental output against a fresh full rebuild using the same next-day data.

Then I compared every Customer 360 row in both directions.

Result:

```text
incremental minus full = 0
full minus incremental = 0
```

All 100,000 customer rows matched exactly.

Only after that did the performance result matter.

## I chose the simpler architecture

This was the engineering decision I wanted the benchmark to produce.

Incremental processing works.

It is faster.

But the original full Customer 360 already completes in 3.43 seconds for 100,000 customers.

Incremental processing adds:

- affected-customer detection,
- temporal-boundary logic,
- partial rebuild logic,
- state management,
- more reconciliation,
- more failure modes.

At the current scale, that complexity is not necessary.

So SignalDesk keeps:

> **full refresh as the default**

while retaining the incremental implementation as a measured optimization path if scale, cost, or SLA requirements change.

That is a more useful result than simply saying I built an incremental pipeline.

## What this changed about how I think about AI systems

It is easy to focus on models, prompts, RAG, and agents.

But before an agent can reason about a customer, someone still has to decide:

- which identity is the customer,
- which events are duplicates,
- what a completed purchase means,
- which time period matters,
- how a decline is measured,
- whether a customer can be contacted,
- what missing information means.

Those are semantic-layer decisions.

An LLM can explain:

> Recent purchasing fell substantially while unresolved support issues increased.

But the system should already know, deterministically, how many purchases occurred and how many support issues are unresolved.

That is the boundary I want in SignalDesk:

```text
deterministic system
    calculates facts

probabilistic system
    reasons about facts
```

The next commit finally crosses into LLM engineering.

But now the LLM will receive a Customer 360 I can test, reconcile, and explain rather than a pile of raw customer data and a prompt asking it to figure everything out.
