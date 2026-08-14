# SignalDesk Learning Log

## Commit 01 — Define Customer Problem and Success Metrics

### Hypothesis

The main NovaCart retention problem is not identifying at-risk customers.

The existing model already produces approximately 2,000 at-risk customers each week.

The primary bottleneck is the Retention team's ability to investigate those customers and make informed intervention decisions at scale.

### What We Started With

Initial problem framing:

"Build an AI agent that identifies customers likely to churn and automatically sends retention discounts."

This combined several separate problems:

- Churn identification
- Customer investigation
- Intervention selection
- Action execution

### What Changed During Discovery

We narrowed the V1 problem to:

"Help Retention Specialists investigate customers already identified as at risk, understand the evidence behind declining engagement, and determine an appropriate intervention while preserving human control over consequential actions."

The V1 intervention choices are:

- `NO_ACTION`
- `RETENTION_OFFER`
- `ESCALATE_TO_SUPPORT`

### Key Design Decisions

#### 1. Do not replace the existing risk model

Reason:

Discovery indicates that NovaCart already has an upstream system producing the at-risk population.

The unresolved bottleneck is investigation capacity, not customer identification.

#### 2. Separate investigation from intervention

Investigation answers:

"What appears to be happening with this customer?"

Intervention answers:

"What should we do?"

These should eventually be evaluated independently.

#### 3. Separate recommendation from execution

V1 follows:

Investigation
→ Recommendation
→ Evidence
→ Human Review
→ Final Decision

A system-generated recommendation must not automatically execute a consequential customer action.

#### 4. Keep deterministic facts deterministic

Values such as:

- Purchase frequency
- Days since last purchase
- Support-ticket count
- Offer eligibility
- Consent status

should come from authoritative data or deterministic calculations rather than probabilistic inference.

#### 5. Separate customer facts from business knowledge

Structured customer facts and unstructured policies/playbooks have different access patterns and should remain logically separate.

This distinction may later justify SQL/tool access for structured data and retrieval for unstructured knowledge.

#### 6. Separate operational and analytical user experiences

Retention Specialists need a customer-level investigation surface.

Retention Managers need an aggregate analytics surface.

Both should share the same underlying investigation and decision records.

### Quantified Discovery Baseline

Known baseline:

- Approximately 2,000 at-risk customers per week
- Approximately 15% investigated
- Approximately 300 customers investigated per week
- Approximately 1,700 customers not investigated
- Investigation time: 20–30 minutes per customer

Using the 25-minute midpoint:

- Current investigation effort:
  300 × 25 minutes = 7,500 minutes
  ≈ 125 specialist-hours/week

- Full manual coverage:
  2,000 × 25 minutes = 50,000 minutes
  ≈ 833 specialist-hours/week

Full coverage across the 20–30 minute range would require approximately 667–1,000 specialist-hours per week.

### Initial Success Targets

- Investigation coverage: ~15% → ≥80%
- Investigation time: 20–30 minutes → <3 minutes
- Decision quality: ≥85% on labeled evaluation scenarios
- Evidence quality: ≥95% of material claims supported
- System responsiveness: p95 <8 seconds

These are initial engineering hypotheses rather than validated production outcomes.

### Requirements Produced

- 3 personas
- 5 workflows
- 10 functional requirements
- 5 non-functional requirements
- 5 primary success metrics
- More than 5 explicit assumptions
- More than 5 open questions
- 1 V0 architecture

### Most Important Lesson

Requirements should justify architecture.

Architecture should not invent requirements simply to justify interesting technology.

Instead of starting with:

"We should use LangGraph, RAG, and a vector database."

Start with:

"What customer workflow are we changing?"

Then derive:

Pain
→ Workflow
→ Decision
→ Requirement
→ Architecture
→ Technology

### Tradeoffs

#### Human review vs full automation

Human approval limits automation in V1 but reduces the risk of unvalidated recommendations directly affecting customers.

Decision:

Automate investigation before automating consequential action.

#### Scope vs ambition

Replacing the risk model could make the project more technically complex, but discovery does not justify doing so.

Decision:

Keep the existing model upstream and solve the demonstrated investigation bottleneck first.

#### Management UI vs shared UI

A single UI would be simpler initially.

However, Retention Specialists and Retention Managers perform fundamentally different jobs.

Decision:

Use separate operational and analytical surfaces backed by shared data.

### What I Can Explain Now

I can explain:

- Why churn prediction and retention intervention are different problems.
- Why a likely-to-churn customer is not necessarily a good discount candidate.
- Why investigation, recommendation, and execution should be separate stages.
- Why deterministic customer facts should remain outside probabilistic reasoning.
- Why human approval must represent real judgment rather than ceremonial clicking.
- Why success metrics must measure customer workflow outcomes, not just API performance.
- Why architecture should follow validated requirements.

### What Is Still Unproven

We have not yet demonstrated:

- That SignalDesk can reduce investigation time below 3 minutes.
- That ≥80% weekly investigation coverage is operationally achievable.
- That intervention recommendations can exceed 85% evaluation accuracy.
- That evidence support can exceed 95%.
- That the system can respond with p95 latency below 8 seconds.
- That SignalDesk improves real-world retention, revenue, or promotion ROI.

Those claims require implementation and measurement in later commits.

### Could I Rebuild This Reasoning From Scratch?

Target answer before closing Commit 01:

Yes — I should be able to start with an ambiguous customer request, separate the underlying problems, identify users and workflows, define measurable outcomes, derive requirements, and propose a technology-neutral architecture.

---

## Commit 02 — Build a Synthetic CDP for AI Engineering Experiments

### Hypothesis

SignalDesk needs a realistic synthetic customer-data environment before we can build customer investigation, retrieval, or agent workflows.

A useful synthetic CDP should not merely generate valid-looking rows. It should preserve relationships, intentionally contain realistic data-quality problems, encode observable customer behavior patterns, and remain testable at scale.

### Starting point

The initial temptation was to generate large amounts of data using Faker and move on.

That would have created volume without proving that the data actually represented the business scenarios SignalDesk needs to investigate.

Instead, the synthetic-data work was treated as an engineering system with its own contracts, truth layer, validation, and scale benchmarks.

### Structured CDP model

The final synthetic CDP contains 12 core domains:

- `customers`
- `identities`
- `sessions`
- `events`
- `products`
- `orders`
- `order_items`
- `support_tickets`
- `campaigns`
- `campaign_exposures`
- `subscriptions`
- `consent_preferences`

The generator intentionally models:

- anonymous-to-known identity transitions,
- duplicate raw events,
- late-arriving events,
- profile nulls,
- mixed timezones,
- refunded and canceled orders,
- unresolved support issues,
- campaign engagement differences,
- subscription-state differences,
- deterministic communication consent.

### Synthetic behavioral scenarios

The generator uses hidden customer-generation patterns:

- `stable`
- `declining_engagement`
- `support_issue`
- `price_sensitive`
- `dormant`

These labels influence the generated rows but are not exposed to SignalDesk's production-like data.

A separate test-only truth layer is emitted under:

`_truth/customer_generation_truth`

This gives the validation framework an answer key without leaking the answer into the application data.

### Structural validation

The validator verifies:

- required tables,
- primary-key behavior,
- foreign-key integrity,
- order-to-order-item reconciliation,
- event duplication,
- event ingestion lag,
- anonymous activity,
- profile null rates,
- campaign references,
- subscription references,
- consent references,
- effective opt-out enforcement.

At the final scale benchmark:

- order reconciliation mismatches: `0`,
- effective consent opt-out violations: `0`.

### Semantic validation

Structural correctness was not enough.

The first semantic test exposed a generator bug: customers labeled `declining_engagement` did not reliably show lower activity in the recent 60-day window.

Initial declining-behavior pass rate:

`46.7%`

Target:

`>= 75%`

Rather than lowering the target, the generator was changed so the prior and recent 60-day windows produced an observable decline.

At 100,000 customers:

- declining-behavior pass rate: `91.374%`,
- support-issue ticket lift vs stable: `33.976x`,
- price-sensitive discount lift vs stable: `+57.757 percentage points`,
- dormant mean recent sessions/customer: `0.093`,
- price-sensitive campaign click lift vs stable: `+17.68 percentage points`,
- stable active-subscription rate: `35.479%`,
- dormant active-subscription rate: `1.943%`.

### Scale benchmark

The completed 100K-customer benchmark produced:

- customers: `100,000`,
- identities: `296,894`,
- products: `1,000`,
- campaigns: `60`,
- campaign exposures: `322,063`,
- subscriptions: `44,053`,
- consent preferences: `300,000`,
- orders: `478,253`,
- order items: `861,226`,
- support tickets: `27,414`,
- sessions: `997,663`,
- raw events: `3,576,871`.

Total production-like rows:

`7,005,497`

Benchmark result:

- generation wall time: `42.02 seconds`,
- throughput: `166,717 rows/second`,
- Parquet dataset size: `239.635 MB`,
- structural validation: `PASS`,
- semantic validation: `PASS`.

Data-quality controls remained close to their configured values:

- duplicate event rate: `0.983%`,
- late-event rate: `4.008%`,
- profile null rate: `3.035%`,
- anonymous session rate: `4.487%`.

### Scaling tradeoff: CSV to Parquet

The generator and validators worked correctly at smaller scale, but larger CSV runs exposed I/O and repeated-scan bottlenecks.

The storage and validation design was changed only after measurement:

- small development data can remain easy to inspect,
- large benchmark runs use Parquet,
- Parquet is written in batches,
- scale validation uses streaming/sequential-ID contracts rather than repeatedly materializing large ID sets.

The lesson was:

> Measure the bottleneck first, then change the architecture.

### Deterministic consent

Consent became an important example of separating deterministic constraints from probabilistic behavior.

If a customer's channel status is effectively `OPTED_OUT` before a campaign send time, the generator must not create an exposure on that channel.

The final validation result was:

`0` effective opt-out violations.

This is the same principle SignalDesk will later use: an AI recommendation cannot override a hard eligibility or consent rule.

### Synthetic business knowledge

SignalDesk also needs an unstructured knowledge environment.

A corpus of `1,000` synthetic Markdown documents was generated across:

- retention,
- offers,
- support,
- shipping,
- refunds,
- loyalty,
- campaigns,
- subscriptions,
- consent.

The corpus intentionally includes current policies, superseded policies, drafts, incomplete documents, playbooks, procedures, FAQs, and operating guides.

Final corpus status distribution:

- `CURRENT`: 694,
- `SUPERSEDED`: 153,
- `DRAFT`: 97,
- `INCOMPLETE`: 56.

The final corpus validation passed all checks for document count, IDs, metadata, content length, domain coverage, status mixture, approved-policy coverage, and known knowledge gaps.

### Knowledge gaps are intentional

The corpus deliberately does not provide authoritative answers for some questions, including:

- exact causal uplift from retention discounts,
- optimal customer-specific discount percentage,
- automatic execution of retention actions,
- compensation beyond documented service-recovery limits.

This creates future evaluation cases where SignalDesk should return insufficient evidence or require human review instead of hallucinating policy.

### Key design decisions

1. Generate correlated customer behavior rather than independent random tables.
2. Keep generator truth separate from production-like application data.
3. Test structural correctness and semantic realism separately.
4. Treat failed semantic tests as generator defects.
5. Preserve realistic data-quality problems intentionally.
6. Scale only after correctness is established.
7. Change storage architecture only after measuring the bottleneck.
8. Keep hard consent rules deterministic.
9. Model unstructured knowledge as messy and versioned rather than pristine.
10. Deliberately include missing knowledge so future systems can be tested for abstention.

### What I learned

Synthetic data is a product, not a pile of fake rows.

A useful synthetic dataset needs:

> Schema validity + relational integrity + semantic realism + controlled messiness + measurable scale

I also learned that a dataset can be structurally perfect and still be semantically useless.

The hidden truth layer gave us a way to test whether observable behavior actually matched the scenario that generated it.

The knowledge-corpus work added another lesson: RAG cannot retrieve knowledge that does not exist. In a real deployment, the FDE may first need to discover where knowledge actually lives, determine what is authoritative, formalize hard rules, and create durable knowledge before retrieval is useful.

### Before/after

**Before**

- no synthetic customer environment,
- no reproducible behavioral scenarios,
- no structural validation,
- no semantic truth layer,
- no scale benchmark,
- no synthetic policy corpus.

**After**

- 12-domain synthetic CDP,
- 100K customers,
- ~7M production-like rows,
- ~3.58M behavioral events,
- ~478K orders,
- structural and semantic validation,
- deterministic consent enforcement,
- Parquet scale path,
- 1,000-document synthetic business-knowledge corpus,
- explicit knowledge gaps for future abstention tests.

### Still unproven

Commit 02 does not prove:

- that these synthetic distributions match real production distributions,
- that an LLM can reason correctly over the data,
- that retrieval will find the right policy,
- that SignalDesk recommendations are correct,
- that synthetic scenarios predict real customer outcomes,
- that retention interventions cause incremental retention.

Those questions belong to later commits.

### Can I explain/rebuild this from scratch?

**Target: Yes.**

I should be able to explain:

- why synthetic data needs semantic ground truth,
- why truth labels must not leak into application data,
- the difference between structural and semantic validation,
- why the first declining-engagement generator failed,
- why Parquet was introduced only after scale measurements,
- why consent remains deterministic,
- why business-knowledge gaps are intentionally part of the corpus.

---

## Next

Commit 03 will transform the raw synthetic CDP into deterministic customer-level features and a customer-360 layer that SignalDesk can query reliably.

---

## Commit 03 — Raw to Customer 360

### Hypothesis

SignalDesk should not ask an LLM to calculate basic customer facts from raw CDP data.

Before probabilistic reasoning is introduced, the system needs a deterministic semantic layer that resolves identity, standardizes business definitions, applies reproducible time windows, and exposes customer evidence in a form that can be tested and reconciled.

The initial hypothesis was:

> DuckDB + SQL can transform the synthetic CDP into a trustworthy one-row-per-customer semantic layer fast enough that correctness and simplicity matter more than premature distributed processing.

### Architecture

Commit 03 uses:

- Parquet / CSV as raw storage,
- DuckDB as the analytical engine,
- SQL for deterministic transformations,
- Python for orchestration, benchmarking, and validation.

The transformation graph is:

```text
raw
 ↓
staging
 ↓
domain feature marts
 ↓
customer_360
```

The final grain is:

> exactly one row per resolved NovaCart customer.

### Semantic contract

Before writing the transformations, the Customer 360 contract defined:

- one explicit customer grain,
- an `as_of_ts`,
- exact 30/60/90/120-day window semantics,
- successful-order definitions,
- null vs zero behavior,
- identity-resolution rules,
- PII boundaries,
- deterministic feature definitions.

The layer intentionally excludes raw email, phone, date of birth, and address fields.

It also does **not** create a new `churn_signal`.

Commit 01 established that NovaCart already has an upstream at-risk model. Commit 03 therefore exposes deterministic evidence that can explain risk instead of silently replacing the existing model.

Examples include:

- `purchase_decline_flag`,
- `engagement_decline_flag`,
- `support_attention_flag`.

### Identity resolution

Raw sessions and events may be anonymous at collection time.

Staging therefore preserves:

```text
observed_customer_id
resolved_customer_id
```

The resolved key is derived through the identity table when possible.

This lets Customer 360 recover pre-login activity without rewriting history or pretending the original source already knew the customer.

### Deterministic feature layer

Customer 360 now exposes deterministic features across:

- identity,
- purchase behavior,
- behavioral engagement,
- support,
- campaign interaction,
- subscriptions,
- consent.

Examples include:

- lifetime orders and revenue,
- orders in recent and prior windows,
- purchase change percentage,
- preferred category,
- session counts,
- engagement change,
- product views and cart additions,
- support-case counts and sentiment,
- email delivery/open/click rates,
- active subscriptions,
- current channel consent.

### Full-refresh benchmark

The completed 100K-customer build produced:

- source customers: `100,000`,
- Customer 360 rows: `100,000`,
- transform runtime: `3.43 seconds`,
- throughput: `29,150.57 customers/second`.

Validation result:

- tests: `33`,
- passed: `33`,
- failed: `0`.

The tests verify:

- one-row-per-customer grain,
- uniqueness and completeness,
- valid temporal ordering,
- nested time-window consistency,
- non-negative revenue and counts,
- bounded rates,
- deterministic decline-flag definitions,
- support reconciliation,
- campaign funnel consistency,
- subscription constraints,
- reproducible `as_of_ts`.

### First implementation failure

The first DuckDB execution failed because several aggregate CTEs referenced `ctx.as_of_ts` inside filtered aggregates without grouping by it.

DuckDB raised a binder error.

The fix was to make the grouping contract explicit:

```sql
GROUP BY customer_id, as_of_ts
```

across the affected purchase, engagement, support, campaign, and subscription transformations.

This was a useful reminder that syntax-checking Python is not enough to validate SQL execution semantics.

### Incremental-processing hypothesis

After the full-refresh baseline passed, I tested whether an incremental Customer 360 would materially improve performance.

The first naive idea would be:

```text
new source rows
→ recompute those customers
```

That is incorrect for a time-windowed semantic layer.

A customer can change without receiving new data because an existing fact may cross a 30/60/90/120-day boundary.

Therefore:

```text
affected customers
=
data-changed customers
UNION
time-boundary-affected customers
```

### Durable facts vs volatile recency

The initial Customer 360 materialized relative values such as:

- `days_since_purchase`,
- `days_since_last_seen`,
- `days_since_last_support_case`,
- `days_since_last_campaign`.

Advancing the semantic clock by one day would make many rows stale even if no business event changed.

The incremental-aware design instead materializes absolute timestamps such as:

- `last_purchase_at`,
- `last_seen_at`,
- `last_support_case_at`,
- `last_campaign_at`.

Relative `days_since_*` fields are derived in the final Customer 360 view from those durable timestamps and `runtime_context`.

This separates:

> durable customer fact

from:

> interpretation relative to the current as-of timestamp.

### Incremental benchmark

A controlled next-day benchmark advanced the semantic clock by 24 hours.

Source-data changes were generated for:

`2,000 customers` (`2%` of the population).

However, after including time-window expiry, the actual affected set became:

`23,645 customers`

or:

`23.645%` of the population.

That means a 2% source-data change expanded into almost 12x as many semantically affected customers.

Measured timings:

- delta apply: `0.2321 seconds`,
- affected-customer detection: `0.2103 seconds`,
- incremental feature recomputation: `0.3769 seconds`,
- incremental semantic total: `0.5872 seconds`,
- full-reference feature recomputation: `0.9573 seconds`.

Feature-only incremental speedup:

`2.54x`

When affected-customer detection is included, the effective semantic speedup is approximately:

`1.63x`

### Incremental reconciliation

Performance was not accepted without equivalence.

The benchmark applied the same delta to:

- an incremental database,
- a fresh full-reference database.

The outputs were compared in both directions:

```sql
incremental_customer_360
EXCEPT
full_customer_360
```

and:

```sql
full_customer_360
EXCEPT
incremental_customer_360
```

Results:

- incremental rows: `100,000`,
- full-reference rows: `100,000`,
- incremental minus full: `0`,
- full minus incremental: `0`,
- exact match: `true`.

### Engineering decision

Incremental processing works and is exactly reconcilable.

However, the full 100K Customer 360 already completes in `3.43 seconds`.

The incremental semantic layer reduces feature computation, but the practical gain at this scale is modest once affected-customer detection and operational complexity are included.

Therefore the current decision is:

> Keep full refresh as the default architecture at 100K customers.

The incremental implementation remains as a proven optimization path for a future scale, SLA, or compute-cost requirement.

This decision avoids adding permanent complexity for a problem that is already solved cheaply.

### Key tradeoffs

**Full refresh vs incremental**

Full refresh is simpler, easier to reason about, and already fast enough.

Incremental processing adds:

- affected-customer detection,
- time-boundary logic,
- partial feature-mart rebuilding,
- state management,
- reconciliation requirements,
- more operational failure modes.

The measured benefit does not yet justify making it the default.

**Materialized recency vs derived recency**

Materializing `days_since_*` is convenient but creates unnecessary daily rewrites.

Storing durable timestamps and deriving recency at query time produces cleaner semantics and better incremental behavior.

**Composite risk score vs deterministic evidence**

A composite score might be convenient for an AI prompt, but it would hide business logic and duplicate the upstream at-risk model.

The semantic layer therefore exposes inspectable evidence instead.

### What I learned

An AI application still depends on traditional semantic-layer engineering.

Before the LLM can reason about a customer, someone must define:

- which identity is the customer,
- which events are duplicates,
- what counts as a successful order,
- which time window is being compared,
- what null means,
- what zero means,
- how support attention is defined,
- which consent state is current.

Those decisions are deterministic engineering decisions, not prompting problems.

I also learned that incremental processing for time-windowed models is more subtle than CDC.

A dataset can change semantically even when no new row arrives.

Finally, I learned that optimization should end with a decision, not just a benchmark.

The incremental implementation was correct and faster, but the full refresh remained the better default because the baseline was already cheap and the incremental complexity was not yet justified.

### Before/after

**Before**

- raw domain-level CDP tables,
- anonymous and known activity mixed at source level,
- no deterministic customer-level semantic contract,
- no tested feature mart,
- no full-refresh benchmark,
- no incremental equivalence experiment.

**After**

- explicit Customer 360 contract,
- resolved identity semantics,
- deterministic domain feature marts,
- one-row-per-customer semantic layer,
- 100K-customer build in 3.43 seconds,
- 33/33 data tests passing,
- incremental-processing implementation,
- time-boundary-aware affected-customer detection,
- exact incremental/full reconciliation,
- evidence-based decision to keep full refresh as the default.

### Still unproven

Commit 03 does not prove:

- that the feature definitions match a real production company's semantic definitions,
- that the upstream at-risk model is correct,
- that these features are sufficient for an LLM investigation,
- that the Customer 360 should remain a single wide model at much larger scale,
- that DuckDB is the correct production warehouse technology,
- that incremental processing becomes worthwhile at larger scale.

Those questions require later system behavior and measurements.

### Can I explain/rebuild this from scratch?

**Target: Yes.**

I should be able to explain:

- why the semantic contract was defined before SQL,
- why raw anonymous activity keeps both observed and resolved identity,
- why an LLM should not calculate basic customer metrics,
- why `churn_signal` was deliberately excluded,
- why `as_of_ts` must be explicit,
- why time-window expiry affects incremental processing,
- why absolute timestamps are more durable than materialized `days_since_*`,
- how incremental output was reconciled against a full rebuild,
- why the measured speedup did not automatically justify adopting incremental processing.

---

## Next

Commit 04 will introduce the first LLM calls over deterministic Customer 360 JSON.

The next goal is to learn the LLM request lifecycle, structured outputs, retries, latency, token usage, cost, and probabilistic behavior without adding RAG or an agent framework yet.