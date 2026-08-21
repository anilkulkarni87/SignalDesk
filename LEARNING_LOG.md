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


## Commit 04 — LLM API Playground

### Hypothesis

SignalDesk should introduce LLM reasoning only after deterministic customer facts are available.

The goal of Commit 04 was not to build an agent or RAG system. It was to learn the LLM request lifecycle directly:

- structured inputs,
- structured outputs,
- retries,
- streaming,
- latency,
- token usage,
- reasoning effort,
- cost,
- evaluation of probabilistic behavior.

The working hypothesis was:

> A lightweight model with strict structured output should be sufficient to interpret deterministic Customer 360 evidence without requiring additional reasoning compute.

---

### Architecture

The first probabilistic component was deliberately small:

```text
Customer 360
    ↓
Python / OpenAI Responses API
    ↓
Strict structured assessment
```

The LLM receives a bounded Customer 360 snapshot and returns:

```text
risk_level
summary
evidence[]
recommended_investigation[]
limitations[]
```

This commit intentionally does **not** include:

- RAG,
- policy documents,
- tool calling,
- agents,
- LangGraph,
- action execution.

The purpose was to learn the primitive before adding orchestration.

---

### Deterministic vs probabilistic boundary

The model may decide which Customer 360 features are relevant, but it does not own their values.

For example, the model can return:

```json
{
  "feature": "orders_60d",
  "interpretation": "Recent purchasing is lower than the comparison period."
}
```

Application code then retrieves the actual `orders_60d` value from Customer 360.

This preserves the boundary:

```text
deterministic system
    calculates customer facts

probabilistic system
    interprets customer facts
```

This prevents the LLM from becoming the source of truth for metrics that SQL can calculate deterministically.

---

### First API request

The first request used:

```text
model: gpt-5.6-luna
reasoning effort: none
```

Result:

- API call succeeded,
- strict output schema passed,
- retry attempts: `1`,
- latency: `5.4377 seconds`,
- input tokens: `1,056`,
- output tokens: `376`,
- reasoning tokens: `0`,
- total tokens: `1,432`,
- estimated cost: `$0.003312`.

The assessment referenced only valid Customer 360 features, and application code attached the deterministic feature values afterward.

This demonstrated that structured model reasoning could be layered on top of the semantic layer without giving the model ownership of customer metrics.

---

### Streaming experiment

A separate streaming request was implemented to observe the API event lifecycle directly.

The experiment returned incremental text chunks while the response was generated.

The key learning was:

> Streaming changes how a response is delivered. It does not change the semantic responsibilities of the model.

For SignalDesk, streaming may later improve perceived UI responsiveness, but it does not replace evaluation, structured output, or deterministic customer facts.

---

### Initial 30-case evaluation

A 30-case evaluation set was generated from Customer 360.

Version 1 contained five scenario types:

```text
multiple warning signals
purchase decline only
engagement decline only
support attention only
no warning signals
```

Each scenario contained six customers.

The expected labels were an evaluation rubric over observable Customer 360 evidence.

The hidden synthetic generation truth was deliberately not used.

These labels therefore represented an application-level evaluation contract, not a production churn model.

---

### V1 evaluation result

Configuration:

```text
model: gpt-5.6-luna
reasoning: none
prompt: commit04_v1
```

Results:

| Metric | Result |
|---|---:|
| API success | 100% |
| Schema validity | 100% |
| V1 rubric agreement | 83.33% |
| Required evidence coverage | 90% |
| Evidence-feature validity | 100% |
| Mean latency | 3.6555s |
| p50 latency | 3.5404s |
| p95 latency | 4.5735s |
| Mean input tokens | 1,056.4 |
| Mean output tokens | 402.73 |
| Total estimated cost | $0.104184 |
| Mean cost/request | $0.0034728 |

At first glance, the model appeared to have five classification failures.

Manual inspection showed that the more important failure was in the evaluation design.

---

### The V1 evaluation itself was flawed

V1 assigned expected labels primarily from:

```text
purchase_decline_flag
engagement_decline_flag
support_attention_flag
```

The model, however, received a much richer Customer 360 containing features such as:

```text
days_since_purchase
refund_rate_90d
customer_status
support severity
CSAT
subscription state
campaign engagement
```

This created contradictory evaluation examples.

Examples included:

#### Support-only case expected MEDIUM

Observed evidence also included:

```text
220 days since purchase
2 open support cases
1 negative support case
1 high-priority support case
```

The model returned `HIGH`.

That was a defensible interpretation of the supplied evidence.

#### Another support-only case expected MEDIUM

Observed evidence included:

```text
195 days since purchase
100% recent refund rate
2 open cases
3 negative cases
1 high-priority case
low CSAT
customer_status = PAUSED
```

The model again returned `HIGH`.

The expected MEDIUM label was weaker than the actual evidence.

#### No-warning case expected LOW

The three warning flags were false, but:

```text
customer_status = CLOSED
```

The model returned `MEDIUM`.

Again, the model was using information that the case generator had ignored.

Therefore:

> V1's `83.33%` should be interpreted as rubric agreement, not clean model accuracy.

---

### Evidence-schema defect discovered

V1 also exposed a schema-design defect.

Features such as:

```text
customer_status
```

were supplied to the model and could influence its reasoning, but were not all permitted by the structured `EvidenceFeature` schema.

This created a situation where the model could reason from a fact without being allowed to formally cite it.

The evidence schema was expanded so material model inputs could also become auditable evidence references.

---

### Evaluation V2

The correct response to V1 was **not** to immediately modify the prompt.

Instead, the evaluation dataset was fixed.

V2 selected cleaner cases whose broader Customer 360 evidence was consistent with the intended expected label.

The model and prompt remained unchanged.

This established an important principle:

> When an eval fails, investigate the evaluation contract before optimizing the model.

---

### V2 baseline — Luna / reasoning none

The corrected 30-case evaluation produced:

| Metric | Result |
|---|---:|
| Cases | 30 |
| Successful API calls | 30 |
| API success | 100% |
| Schema validity | 100% |
| V2 rubric agreement | 90% |
| Required evidence coverage | 76.67% |
| Evidence-feature validity | 100% |
| Mean latency | 3.3522s |
| p50 latency | 3.2860s |
| p95 latency | 4.0253s |
| Mean input tokens | 1,048.77 |
| Mean output tokens | 392.5 |
| Reasoning tokens | 0 |
| Total cost | $0.102113 |
| Mean cost/request | $0.00340377 |

Rubric agreement by scenario:

| Scenario | Agreement |
|---|---:|
| Multiple warning signals | 83.33% |
| Purchase decline only | 83.33% |
| Engagement decline only | 83.33% |
| Support attention only | 100% |
| No warning signals | 100% |

The V2 baseline crossed the initial `>=85%` behavioral target.

---

### Correct classification is not enough

V2 produced:

```text
V2 rubric agreement        = 90%
required evidence coverage = 76.67%
```

This exposed another important distinction:

> A correct conclusion does not guarantee a complete evidence trail.

The model could produce the expected risk classification while omitting evidence that the evaluation considered important.

For SignalDesk, this matters because a Retention Specialist needs more than a classification.

They need an explanation that can be inspected and challenged.

Structured Outputs solved:

```text
response shape
field types
allowed evidence keys
```

They did not automatically solve:

```text
reasoning quality
classification quality
evidence completeness
```

---

### Controlled reasoning-effort experiment

After establishing the V2 baseline, exactly one variable was changed:

```text
reasoning effort:
none → low
```

The following remained fixed:

```text
same model
same prompt
same output schema
same 30 V2 customers
same evaluation rubric
```

This made it a controlled experiment.

---

### Luna / reasoning low

Results:

| Metric | Result |
|---|---:|
| API success | 100% |
| Schema validity | 100% |
| V2 rubric agreement | 90% |
| Required evidence coverage | 66.67% |
| Evidence-feature validity | 100% |
| Mean latency | 3.5848s |
| p50 latency | 3.3768s |
| p95 latency | 4.3934s |
| Mean input tokens | 1,048.77 |
| Mean output tokens | 436.43 |
| Total reasoning tokens | 1,426 |
| Mean reasoning tokens/request | 47.53 |
| Maximum reasoning tokens/request | 117 |
| Total cost | $0.110021 |
| Mean cost/request | $0.00366737 |

---

### Reasoning experiment comparison

| Metric | Luna / none | Luna / low |
|---|---:|---:|
| V2 rubric agreement | **90.0%** | **90.0%** |
| Required evidence | **76.67%** | 66.67% |
| API success | 100% | 100% |
| Schema validity | 100% | 100% |
| Evidence-feature validity | 100% | 100% |
| Mean latency | **3.3522s** | 3.5848s |
| p95 latency | **4.0253s** | 4.3934s |
| Mean input tokens | 1,048.77 | 1,048.77 |
| Mean output tokens | **392.5** | 436.43 |
| Total reasoning tokens | **0** | 1,426 |
| Mean reasoning tokens/request | **0** | 47.53 |
| Mean cost/request | **$0.00340377** | $0.00366737 |

The additional `1,426` reasoning tokens produced:

```text
0 percentage-point improvement
```

in V2 rubric agreement.

They also produced:

```text
lower evidence completeness
higher latency
more output tokens
higher cost
```

---

### Engineering decision

For this structured Customer 360 interpretation workload, the current default is:

```text
model: gpt-5.6-luna
reasoning effort: none
```

Why:

```text
90% V2 rubric agreement
100% schema validity
100% evidence-feature validity
better evidence coverage than reasoning=low
lower latency
lower token consumption
lower cost
```

The conclusion is workload-specific.

It does **not** mean reasoning tokens are generally useless.

It means:

> Additional reasoning compute must demonstrate measurable value for the specific task before being adopted.

For this task, it did not.

---

### What failed

Commit 04 produced several useful failures:

#### Import/package failure

Running:

```bash
python evals/commit04/runner.py
```

failed because the nested script execution changed Python's import path.

The evaluation package was changed to use module execution:

```bash
python -m evals.commit04.runner
```

#### V1 rubric failure

The initial evaluation labels ignored important Customer 360 evidence.

Manual failure analysis showed that several apparent model errors were actually ambiguous evaluation cases.

#### Evidence-schema failure

Some supplied model features could affect reasoning but could not be formally cited.

The schema was corrected.

These failures reinforced that AI engineering problems can exist in:

```text
application code
prompt
schema
evaluation dataset
gold labels
metrics
model behavior
```

The model is only one possible source of failure.

---

### What I learned

#### 1. Deterministic and probabilistic systems need different tests

Customer 360 produced:

```text
33 tests
33 deterministic passes
```

The LLM produced:

```text
30 successful requests
30 schema-valid responses
27 V2 classifications matching the rubric
```

Nothing crashed.

The output was structurally valid.

Yet behavior still differed from expectations.

That is why AI systems require behavioral evals in addition to unit and integration tests.

#### 2. Structured output is not correctness

I achieved:

```text
100% schema validity
```

but only:

```text
90% V2 rubric agreement
```

A perfectly formed JSON object can still contain the wrong decision.

#### 3. Valid evidence is not complete evidence

The model achieved:

```text
100% evidence-feature validity
```

but only:

```text
76.67% required-evidence coverage
```

The model never cited a nonexistent feature.

It still sometimes omitted important evidence.

This is important for explainable customer workflows.

#### 4. Evals are software

The first evaluation set was itself defective.

Gold labels should not be treated as unquestionable truth.

They need:

```text
design
review
versioning
testing
failure analysis
```

just like application code.

#### 5. Do not optimize the model before understanding the failure

After V1 produced 83.33% agreement, the tempting response would have been:

```text
change prompt
increase reasoning
use larger model
```

Manual review showed that this would have optimized against several bad labels.

Fixing the evaluation first was the correct engineering decision.

#### 6. More reasoning is not automatically better

`reasoning=low` consumed:

```text
1,426 additional reasoning tokens
```

across the 30 cases.

It produced:

```text
no improvement in rubric agreement
worse evidence completeness
higher latency
higher cost
```

The correct question is not:

> Can I give the model more reasoning?

It is:

> Does additional reasoning improve this workload enough to justify its cost?

---

### Before / after

#### Before

```text
deterministic Customer 360
no model calls
no model output contract
no latency baseline
no token measurements
no cost measurements
no behavioral evaluation
no understanding of reasoning-effort tradeoffs
```

#### After

```text
Responses API client
strict structured output
bounded retry behavior
streaming experiment
deterministic evidence attachment
30-case evaluation harness
V1 failure analysis
V2 evaluation rubric
90% V2 rubric agreement
100% schema validity
100% evidence-feature validity
latency measurements
token measurements
cost measurements
controlled reasoning experiment
measured decision to use reasoning=none
```

---

### Still unproven

Commit 04 does not prove:

- real churn prediction accuracy,
- recommendation correctness,
- policy grounding,
- causal impact of retention interventions,
- retrieval quality,
- tool-selection quality,
- agent task completion,
- end-to-end production latency.

The model currently reasons only over a bounded deterministic Customer 360 snapshot.

---

### Can I explain/rebuild this from scratch?

**Target: Yes.**

I should be able to explain:

- why Customer 360 remains the source of deterministic truth,
- why the LLM references features instead of calculating their values,
- how Structured Outputs differ from semantic correctness,
- why behavioral evals are needed in addition to unit tests,
- why V1's 83.33% was partly an evaluation-design problem,
- why fixing the eval was better than immediately modifying the prompt,
- why classification agreement and evidence completeness are separate metrics,
- how latency, tokens, retries, and cost are measured,
- what reasoning tokens represent in the experiment,
- why `reasoning=none` won this workload,
- why model optimization must follow measurement rather than intuition.

---

## Commit 05 - Prompt Evaluation Harness

### Goal

Commit 05 turned the Commit 04 LLM experiment into a prompt regression system.

The learning goal was:

```text
Treat prompts like versioned software artifacts.
```

Instead of asking whether a new prompt "seems better," I wanted to answer:

```text
Did Prompt V2 improve behavior?
Did it introduce regressions?
Did evidence coverage improve?
Did latency, token usage, or cost change?
Which exact cases changed?
```

This commit still deliberately avoided:

- RAG,
- embeddings,
- agents,
- tools,
- policy retrieval.

The model continued to reason only over deterministic Customer 360 snapshots.

---

### What I built

Commit 05 added:

```text
src/llm/prompt_versions/v1.py
src/llm/prompt_versions/v2.py
evals/commit05/cases.jsonl
evals/commit05/make_cases.py
evals/commit05/runner.py
evals/commit05/metrics.py
evals/commit05/compare.py
evals/commit05/reports/
```

V1 is a frozen copy of the released Commit 04 prompt:

```text
prompt = commit04_v1_frozen
model = gpt-5.6-luna
reasoning = none
```

V2 began as a behaviorally identical placeholder.

The rule was important:

```text
Do not change V2 until V1 failures are measured on a fixed case suite.
```

---

### First false start

The first Commit 05 run compared V1 against the placeholder V2.

That was useful only as a repeatability experiment.

It did not prove prompt improvement because:

- V2 was behaviorally identical to V1,
- the case selector had weakened Commit 04 v2 safeguards,
- 24 of 50 cases had ambiguous broader warning evidence,
- `multiple_warning_signals_03` omitted `support_attention_flag` from required evidence.

This repeated a Commit 04 lesson:

```text
If the eval set is wrong, model metrics can look precise while measuring the
wrong thing.
```

So I fixed the evaluation before tuning the prompt.

---

### Clean 50-case suite

I regenerated Commit 05 cases using Commit 04 eval v2 selectors.

The new suite has:

```text
50 total cases
10 multiple warning signal cases
10 purchase decline only cases
10 engagement decline only cases
10 support attention only cases
10 no warning signal cases
```

The selectors intentionally remove contradictory broader evidence from the
single-signal and LOW categories.

Examples:

- LOW cases require active customers with recent purchases, recent sessions, no warning flags, no refunds, and no recent subscription cancellation.
- support-only cases require a material but moderate support issue, while excluding purchase decline, engagement decline, dormant behavior, high-priority cases, heavy negative support volume, refunds, and cancellation.
- multi-warning cases require `purchase_decline_flag` plus at least one independent warning domain.

The regenerated suite passed local validation:

```text
cases: 50
counts: 10 per category
selector violations: 0
rubric_version: commit05_eval_from_commit04_v2_selectors
```

---

### V1 baseline on clean cases

V1 produced:

```text
API success:              100%
schema validity:          100%
evidence feature validity: 100%
risk accuracy:             86%
required evidence:         78%
reasoning tokens:           0
```

The failures were concentrated:

```text
multiple_warning_signals:
  6 / 10 risk correct
  6 / 10 required evidence present

engagement_decline_only:
  7 / 10 risk correct
  9 / 10 required evidence present

support_attention_only:
  10 / 10 risk correct
  6 / 10 required evidence present
```

Manual review showed two measured problems:

1. V1 under-classified some customers with both `purchase_decline_flag` and
   `engagement_decline_flag` as MEDIUM instead of HIGH.
2. V1 sometimes reached the right classification while omitting the exact true
   warning flag from evidence.

This was now a prompt problem, not an eval problem.

---

### V2 hypothesis

V2 became:

```text
commit05_v2_warning_flag_calibration
```

The hypothesis:

```text
V1 under-classified customers with both purchase_decline_flag and
engagement_decline_flag set, and sometimes omitted true warning flags from
evidence. V2 should improve HIGH classification for multiple warning signals
and required-evidence coverage by making the three curated warning flags
explicit decision anchors.
```

The prompt change was intentionally small.

V2 made these rules explicit:

- treat `purchase_decline_flag`, `engagement_decline_flag`, and `support_attention_flag` as curated warning signals,
- cite true warning flags when they influence the assessment,
- classify purchase decline plus engagement decline or support attention as HIGH,
- classify exactly one true curated warning flag as MEDIUM rather than LOW,
- reserve LOW for customers with no curated warning flags and no other material warning signal.

---

### V1 vs V2 result

V2 produced:

```text
API success:              100%
schema validity:          100%
evidence feature validity: 100%
risk accuracy:            100%
required evidence:        100%
reasoning tokens:           0
```

Comparison:

```text
risk accuracy:
  V1: 86%
  V2: 100%
  delta: +14 points

required evidence:
  V1: 78%
  V2: 100%
  delta: +22 points

regressions:
  0

improvements:
  16

changed risk cases:
  7
```

Cost and token impact:

```text
mean input tokens: +139
mean output tokens: -4.3
mean cost/request: +$0.000113
mean latency: -0.0539s
p95 latency: -0.1347s
```

The input-token increase was expected because V2 contains more explicit
calibration rules.

The tradeoff was acceptable for this workload because V2 directly fixed the
measured failures without regressions.

Decision:

```text
Adopt V2 for this evaluation suite.
```

---

### What I learned

#### 1. A prompt comparison needs a fixed input suite

Changing the prompt and the cases at the same time destroys the experiment.

Commit 05 only became meaningful after the 50 Customer 360 inputs were fixed.

#### 2. Repeatability is not improvement

The first V1/V2 comparison looked like a comparison report, but V2 was still a
placeholder.

That run measured model variability and harness behavior, not prompt quality.

#### 3. Prompt changes need hypotheses

The useful V2 change did not come from preference.

It came from measured V1 failures:

```text
under-classified multiple warning signals
missing true warning-flag evidence
```

That made V2 small, reviewable, and testable.

#### 4. Regression count matters as much as average accuracy

An average metric can improve while individual important cases get worse.

The comparison report made regressions explicit.

For this run:

```text
regressions = 0
```

That is why the adoption decision is defensible.

#### 5. Evidence completeness is a separate product quality metric

V2 did not only improve the final risk label.

It improved the explanation trail:

```text
required evidence: 78% -> 100%
```

For SignalDesk, that matters because a human reviewer needs to see the
deterministic facts behind the model's conclusion.

#### 6. More prompt text has a cost

V2 added about 139 input tokens per request.

That is not free.

But the measured gain was large enough to justify the extra cost for now.

---

### Before / after

#### Before

```text
single prompt
one evaluation runner
no prompt version directory
no fixed 50-case prompt regression suite
no V1/V2 comparison report
no regression list
no measured adoption decision
```

#### After

```text
frozen V1 prompt
hypothesis-driven V2 prompt
50 fixed clean evaluation cases
same model and reasoning setting across versions
V1 baseline report
V2 candidate report
comparison report
per-case improvements
regression count
latency, token, and cost deltas
measured decision to adopt V2
```

---

### Still unproven

Commit 05 does not prove:

- real churn prediction accuracy,
- generalization beyond the 50-case suite,
- quality on messy production data,
- policy-grounded recommendations,
- causal intervention impact,
- retrieval quality,
- agent behavior,
- tool-use correctness.

It proves something narrower and useful:

```text
Given this fixed Customer 360 evaluation suite, Prompt V2 improves measured
risk classification and required-evidence coverage over frozen V1 without
observed regressions.
```

---

### Can I explain/rebuild this from scratch?

**Target: Yes.**

I should be able to explain:

- why V1 must stay frozen,
- why V2 starts as a placeholder,
- why eval cases must be fixed before tuning,
- why the first Commit 05 comparison was not proof of prompt improvement,
- how Commit 04 v2 selectors made the 50 cases cleaner,
- how required evidence differs from evidence-feature validity,
- how to read a V1 failure report and form a narrow V2 hypothesis,
- why regression count is a first-class adoption metric,
- why `gpt-5.6-luna` with `reasoning=none` stayed fixed,
- why this still avoids RAG and agents,
- why prompt adoption should be a measured decision, not a vibe check.

---

## Commit 07 Draft - Policy-Grounded Retrieval Built Early

> Roadmap reconciliation: the work recorded in this section combines retrieval
> with LLM generation, policy citations, and customer-tied cases. The original
> SignalDesk roadmap classifies that as Commit 07 RAG groundwork. References to
> "Commit 06" inside this historical section describe the order in which the
> prototype was built, not its final roadmap placement. Commit 06 must first
> measure embeddings and vector search independently.

### Goal

Commit 06 introduced retrieval without introducing agents.

The learning goal was:

```text
Separate customer facts from business policy context.
```

Commit 05 gave me a measured prompt baseline.

Commit 06 added a new input source:

```text
Customer 360 snapshot
  deterministic facts about the customer

Retrieved knowledge documents
  bounded business guidance about policies, procedures, and known gaps

LLM assessment
  interpretation that must keep those two evidence types separate
```

This commit still did not allow the model to execute actions, call tools, update
systems, or act as an agent.

---

### Why retrieval adds a new failure surface

Before retrieval, a bad LLM answer could come from:

```text
bad customer data
bad prompt
bad schema
bad eval case
model behavior
```

After retrieval, a bad answer can also come from:

```text
wrong document retrieved
right document not retrieved
stale source retrieved
draft or incomplete source treated as current
policy context mixed up with customer facts
retrieved context overclaimed by the model
```

That means retrieval needs its own tests before the LLM uses the context.

---

### Corpus used

The knowledge corpus was the generated NovaCart corpus created by:

```bash
python data/knowledge/generate_knowledge_docs_v2.py
```

It contains:

```text
1,000 documents
694 CURRENT docs
153 SUPERSEDED docs
97 DRAFT docs
56 INCOMPLETE docs
330 POLICY docs
4 known knowledge gaps
```

This was the right corpus for Commit 06 because it is intentionally messy:

- overlapping terminology,
- current and stale documents,
- approved and reference material,
- incomplete sources,
- multiple plausible matches,
- known gaps where the correct behavior is abstention.

A tiny hand-written corpus would make the first demo easier, but it would hide
the real retrieval problem.

---

### What I built

Commit 06 added:

```text
src/retrieval/documents.py
src/retrieval/lexical.py
src/retrieval/search.py
src/retrieval/query_planner.py
src/llm/policy_schemas.py
src/llm/prompt_versions/v3.py
evals/commit06/retrieval_cases.jsonl
evals/commit06/retrieval_metrics.py
evals/commit06/make_policy_cases.py
evals/commit06/planner_metrics.py
evals/commit06/policy_cases.jsonl
evals/commit06/policy_runner.py
evals/commit06/policy_metrics.py
README_COMMIT06.md
```

The retriever is deliberately simple and inspectable.

It:

- parses Markdown frontmatter,
- loads generated known gaps as retrievable `GAP-*` sources,
- filters to `CURRENT` and `APPROVED` sources,
- tokenizes text,
- expands a small synonym set,
- scores lexical matches,
- returns document IDs, families, status, authority, matched terms, and excerpts.

This is not meant to be the final retrieval architecture.

It is meant to make retrieval behavior visible.

---

### Retrieval-only evaluation

The first retrieval test did not call the model.

It asked whether the retriever could find the right type of source from the
generated corpus.

Result:

```text
cases: 7
pass rate: 100%
expected doc ID present: 100%
expected family present: 100%
expected top family: 100%
expected status CURRENT: 100%
expected authority APPROVED: 100%
forbidden stale statuses absent: 100%
excerpts present: 100%
```

This tested:

- offer eligibility retrieval,
- support escalation retrieval,
- consent and suppression retrieval,
- causal uplift gap retrieval,
- personalized discount amount gap retrieval,
- automatic execution gap retrieval,
- freshness behavior that excludes stale sources.

---

### Tying retrieval to customers

The first policy-grounded model check used only five hand-written retrieval
queries.

That worked, but it did not fully answer:

```text
How does retrieval tie to a specific customer?
```

The correct bridge is a deterministic policy query planner.

The planner reads Customer 360 facts and chooses policy lookups:

```text
support_attention_flag = true
  -> support escalation / handoff guidance

purchase_decline_flag or engagement_decline_flag = true
  -> retention offer eligibility guidance
  -> known gap for causal discount uplift

email, SMS, or push opt-out = true
  -> consent and suppression guidance

recent_subscription_cancellation_flag = true
  -> subscription cancellation guidance

no warning signals and no channel constraint
  -> general retention review guidance
```

Then `make_policy_cases.py` uses the fixed Commit 05 cases to generate
customer-tied Commit 06 cases:

```text
Commit 05 case
  -> customer_id
  -> Customer 360 snapshot
  -> planned policy queries
  -> expected policy families and gap IDs
```

The expanded suite contains:

```text
25 total cases
5 multiple warning signal cases
5 purchase decline only cases
5 engagement decline only cases
5 support attention only cases
5 no warning signal cases
```

Planner result:

```text
planner eval: 25 / 25 passed
```

---

### Query-planning failure and fix

The first customer-tied version combined all planned policy queries into one
long retrieval query.

That caused a real retrieval problem:

```text
strong consent or offer terms could swamp weaker but important support terms
```

For support-only customers who also had channel opt-outs, the combined query
retrieved consent documents but missed support documents.

The fix was to run each planned policy query separately:

```text
customer snapshot
  -> multiple planned queries
  -> top results per query
  -> deduplicate sources
  -> send merged context to the model
```

That made the bridge reliable:

```text
planner eval: 25 / 25 passed
```

This was an important retrieval lesson:

```text
Query planning matters as much as scoring.
```

---

### Policy-grounded output schema

Commit 06 added policy-specific output fields:

```text
policy_sources
unsupported_policy_claims
```

Customer evidence still cites Customer 360 fields such as:

```text
purchase_decline_flag
engagement_decline_flag
support_attention_flag
orders_60d
email_opted_in
```

Policy sources cite retrieved document IDs such as:

```text
KB-00704
KB-00853
GAP-001
GAP-003
```

That separation matters.

Customer facts answer:

```text
What is true about this customer?
```

Policy sources answer:

```text
What guidance or limits may SignalDesk rely on?
```

---

### Schema-semantics failure and fix

The first 5-case policy-grounded model run produced:

```text
risk accuracy: 100%
policy retrieval: 100%
policy citation: 100%
unsupported policy claims empty: 0%
```

At first, that looked bad.

Manual review showed the schema was ambiguous.

The model used `unsupported_policy_claims` like:

```text
policy limitations or things not established by retrieved context
```

But that was not the intended meaning.

The intended meaning was:

```text
policy claims the assessment actually made without retrieved support
```

So the contract was tightened:

```text
limitations:
  missing facts, uncertainty, and unsupported possibilities not claimed

unsupported_policy_claims:
  unsupported policy claims actually made by the assessment
```

After that fix, the 5-case run passed:

```text
cases: 5
risk accuracy: 100%
policy retrieval: 100%
policy citation: 100%
unsupported policy claims empty: 100%
failures: 0
```

---

### Expanded 25-case policy-grounded result

After tying retrieval to customers and fixing per-query retrieval, the expanded
model evaluation produced:

```text
cases: 25
successful API calls: 25
API success: 100%
risk accuracy: 100%
expected policy retrieval: 100%
expected policy citation: 100%
expected policy family retrieval: 100%
expected policy family citation: 100%
unsupported policy claims empty: 100%
failures: 0
```

This means V3 preserved Commit 05 risk behavior while using retrieved generated
knowledge context and citing policy sources correctly on these 25 customer-tied
cases.

---

### What I learned

#### 1. Retrieval should be tested before generation

If the wrong context is retrieved, the model can produce a bad answer even with
a good prompt.

The retrieval-only eval makes this failure visible before the LLM is involved.

#### 2. Customer facts and policy context are different evidence types

Customer 360 facts should remain deterministic.

Policy context should remain source-cited guidance.

The model should not blur those together.

#### 3. The generated corpus is better than a tiny fixture for this lesson

The generated corpus contains stale, incomplete, overlapping, and non-primary
documents.

That forces the retrieval layer to handle authority and freshness.

#### 4. Query planning is a real system component

One combined query can lose important intent.

Running separate planned queries per customer signal produced better coverage.

#### 5. Output fields need precise semantics

`unsupported_policy_claims` failed because the schema name alone was not enough.

The model needed a clear distinction between:

```text
limitations
unsupported claims
```

#### 6. Known gaps are useful retrieval targets

For questions about causal discount uplift or automatic execution, the right
answer is not another policy.

The right answer is a known gap:

```text
GAP-001
GAP-003
```

That teaches the model when not to overclaim.

---

### Before / after

#### Before

```text
Customer 360 only
no retrieval layer
no policy citations
no freshness filtering
no known-gap retrieval
no customer-driven query planning
no policy-grounded output schema
```

#### After

```text
generated knowledge corpus used as retrieval source
lexical retrieval with source metadata
current approved source filtering
known gaps loaded as retrievable sources
retrieval-only eval
customer-driven policy query planner
25 customer-tied policy cases
planner eval
V3 policy-grounded prompt
policy source citations
unsupported policy claim metric
25-case policy-grounded model eval with zero failures
```

---

### Still unproven

Commit 06 does not prove:

- semantic retrieval quality at production scale,
- embedding retrieval quality,
- ranking quality across all 1,000 documents,
- robustness to adversarial policy conflicts,
- real-world policy correctness,
- intervention recommendation quality,
- agent planning,
- tool-use correctness,
- production latency or caching behavior.

It proves something narrower:

```text
Given the generated NovaCart knowledge corpus and 25 customer-tied cases,
SignalDesk can deterministically plan policy retrieval from Customer 360 facts,
retrieve current approved sources, cite policy context separately from customer
evidence, and avoid unsupported policy claims.
```

---

### Can I explain/rebuild this from scratch?

**Target: Yes.**

I should be able to explain:

- why retrieval was introduced after prompt evaluation,
- why `data/generated/knowledge` is the correct Commit 06 corpus,
- how status and authority metadata affect retrieval,
- why known gaps should be retrievable,
- how Customer 360 facts drive policy query planning,
- why separate planned queries worked better than one combined query,
- how policy sources differ from customer evidence,
- why `unsupported_policy_claims` needed tighter semantics,
- why the LLM still does not execute actions,
- why this is retrieval-grounded generation, not an agent.

---

## Commit 06 - Embeddings and Vector Search

### Roadmap objective

Commit 06 isolates retrieval from answer generation:

```text
document
  -> chunk
  -> embedding
  -> pgvector
  -> cosine similarity search
  -> retrieval metrics
```

The purpose is to learn whether semantic similarity can retrieve NovaCart's
private business knowledge when a user's wording differs from the document's
wording.

This commit does not call `gpt-5.6-luna`, generate an answer, choose a tool, or
execute an action. The generation configuration remains frozen for Commit 07:

```text
model = gpt-5.6-luna
reasoning = none
```

### Hypothesis

OpenAI embeddings plus pgvector cosine search will improve Recall@5 over the
lexical baseline on paraphrased policy questions.

Roadmap target:

```text
Vector Recall@5 > 85%
```

### Frozen inputs

The retrieval dataset contains 50 cases:

- 5 cases for each of 9 generated knowledge families,
- 4 known-knowledge-gap cases,
- 1 cross-family campaign and consent case.

Each case freezes all current approved document IDs matching its curated family
and topic selectors. That avoids arbitrarily declaring one of several equivalent
generated policies to be the only correct result.

For this experiment, Recall@K is the percentage of queries with at least one
curated relevant document in the top K document-level results. MRR measures the
rank of the first relevant document.

### Lexical baseline

The optimized lexical index is built once and reused across all 50 queries.

```text
Recall@1 = 36.0%
Recall@3 = 58.0%
Recall@5 = 68.0%
MRR      = 0.4697
Mean query latency ~= 5 ms
```

The 68% Recall@5 result gives the embedding experiment something real to beat.
Its misses include semantic paraphrases for declining purchases, consent
timestamps, automatic execution gaps, and cross-family suppression rules.

### Implementation

The current implementation adds:

- section-aware chunking with a 220-word maximum and 40-word overlap for long
  sections,
- 1,093 deterministic chunks from 1,004 retrievable records,
- `text-embedding-3-small` embedding batches,
- PostgreSQL plus pgvector storage,
- an HNSW cosine index,
- query-time `CURRENT` and `APPROVED` metadata filtering,
- chunk-to-document deduplication,
- Recall@1, Recall@3, Recall@5, MRR, and latency reporting,
- lexical-versus-vector per-case comparison.

All source documents, including stale and incomplete ones, enter the index.
Authority filtering happens at retrieval time so freshness failures remain
testable.

### Local verification completed

- generated corpus validation passed for 1,000 Markdown documents and 4 known
  gaps,
- 50-case generation test passed,
- chunking and metric unit tests passed,
- Python compilation passed,
- the 7-case policy retrieval smoke test still passed,
- the 25-case customer query planner regression test still passed,
- a real local pgvector integration test passed for schema creation, upsert,
  filtering, document deduplication, HNSW indexing, and cosine ranking using
  synthetic vectors.

### Measured vector result

The real index used:

```text
embedding model      = text-embedding-3-small
embedding dimensions = 1,536
documents            = 1,004
chunks                = 1,093
index input tokens    = 300,972
index embedding time  = 15.150 seconds
total index build     = 18.305 seconds
```

The frozen 50-query comparison produced:

| Metric | Lexical | Vector | Change |
|---|---:|---:|---:|
| Recall@1 | 36.0% | 86.0% | +50.0 points |
| Recall@3 | 58.0% | 92.0% | +34.0 points |
| Recall@5 | 68.0% | 98.0% | +30.0 points |
| MRR | 0.4697 | 0.9007 | +0.4310 |
| Mean end-to-end latency | 4.312 ms | 35.480 ms | +31.168 ms |
| p95 end-to-end latency | 5.129 ms | 40.470 ms | +35.341 ms |

Vector search itself averaged 12.120 ms with p95 17.110 ms. The 35.480 ms
end-to-end mean also includes the query's share of a batched embedding request.

The hypothesis passed. Vector Recall@5 exceeded the 85% roadmap target by 13
percentage points and improved over lexical Recall@5 by 30 points.

### The one remaining miss

Vector retrieval found a relevant document in the top five for 49 of 50 cases.
The miss was:

```text
case:  retention_02
query: What evidence should be reviewed before considering a customer save incentive?
```

The frozen relevant set contains retention-family documents with topic `when a
retention offer may be considered`. The vector top five instead contained
current approved offer-family policies covering eligibility, exclusions, margin
rules, and cooling periods.

This is not a freshness failure. It is an adjacent-family ranking failure. The
query is close to both concepts:

```text
retention decision: should an intervention be considered?
offer eligibility:  is an incentive allowed under policy?
```

I did not relabel the case or tune the retriever after seeing the result. A future
Commit 08 experiment can test whether query decomposition, family-aware hybrid
ranking, or metadata filters resolve this boundary without harming cross-family
questions.

### Tradeoff

Semantic retrieval materially improved relevance but cost more latency:

```text
lexical mean              = 4.312 ms
vector search-only mean   = 12.120 ms
vector end-to-end mean    = 35.480 ms
```

This is an acceptable baseline for the learning system because the original
workflow target is measured in minutes, not milliseconds. It is not proof that
the same tradeoff is acceptable at production concurrency or scale.

### What I learned

- Embeddings solved paraphrase failures that lexical matching could not.
- Retrieval evaluation must be separate from LLM answer evaluation.
- Metadata still matters with vectors; semantic similarity does not determine
  whether a source is current or authoritative.
- Chunk results must be deduplicated before document-level metrics are computed.
- A high average score still needs per-case failure review.
- Similar business concepts can remain difficult even when semantic retrieval is
  strong.
- The honest result is 98%, not a post-hoc tuned 100%.

### Commit 06 conclusion

Commit 06 is complete. It demonstrates an independently measured retrieval layer
with Recall@5 above the roadmap target. The next roadmap step is Commit 07: feed
retrieved policy context into the frozen `gpt-5.6-luna`, `reasoning=none`
generation path and separately evaluate retrieval, answer correctness, citation
correctness, unsupported claims, and latency.

---

## Commit 07 - RAG V1

### Roadmap objective

Commit 07 connects the measured Commit 06 retriever to generation:

```text
explicit question + Customer 360
  -> deterministic policy query planner
  -> vector retrieval
  -> current approved policy context
  -> gpt-5.6-luna, reasoning=none
  -> structured, policy-grounded assessment
```

The learning objective is not merely to produce a plausible answer. Retrieval,
customer-answer correctness, citation correctness, unsupported claims, latency,
tokens, and cost must remain separately measurable.

This is bounded RAG. The model does not select tools, execute actions, update a
system of record, or run an agent loop.

### Frozen evaluation

The 50 clean Commit 05 customer cases remain unchanged. Each customer receives
two questions:

```text
risk_investigation
policy_guardrails
```

That produces 100 frozen questions over 50 Customer 360 profiles. Runtime
policy intents are derived from the same deterministic planner used to freeze
the cases; gold evaluation labels are never passed to the model.

### Retrieval gate

Before generation, all 100 questions passed retrieval and context checks:

```text
retrieval gate pass rate = 100%
expected documents       = 100%
expected families        = 100%
current approved sources = 100%
```

This isolated the next failures to the generation boundary rather than vector
search.

### First full V3 result

The first 100-question run produced:

| Metric | Result |
|---|---:|
| API success | 98.0% |
| Risk correctness | 100% of successful calls |
| Answer correctness | 100% of successful calls |
| Expected policy-family citation | 75.51% |
| Exact excerpt grounding, case rate | 83.67% |
| Exact per-citation precision | 95.17% |
| Unsupported claims empty | 97.96% |
| Reasoning tokens | 0 |
| Estimated generation cost | $0.758971 |

The answer score is 98 successful responses out of 98, not 100 answers out of
100 questions. Two requests timed out.

### Failure classification

The raw records showed four different failure classes:

1. Two transient API timeouts.
2. Twelve quotes existed in another retrieved near-duplicate document but not
   in the document ID selected by the model.
3. Six generated excerpts contained malformed trailing control characters.
4. Twenty-four successful responses omitted at least one policy family required
   by a customer-derived planner intent.

Two responses also returned `unsupported_policy_claims: [""]`. These were
malformed empty entries, not substantive unsupported claims.

The central lesson is:

```text
right documents retrieved
  != every relevant policy used
  != quote attributed to the right document
```

### V4 refinement hypothesis

The V3 result is preserved as a baseline. V4 changes the generation boundary,
not the frozen inputs or retriever:

```text
source content
  -> deterministic bounded quote IDs
  -> model selects quote IDs
  -> application resolves exact document and excerpt
```

The prompt also receives runtime planner intents and must cover each intent that
has an available retrieved source. Individual unsupported-claim strings must be
non-empty, and transient API calls receive bounded measured retries.

The hypothesis is:

> Quote IDs will eliminate malformed and cross-attributed excerpts, while
> explicit planner-intent coverage will raise expected-family citation above
> 90% without reducing customer-answer correctness.

The 100 frozen labels, `gpt-5.6-luna`, `reasoning=none`, retrieval parameters,
and 16,000-character context budget remain unchanged. The next measurement is a
targeted ten-case failure cohort, followed by a fresh 100-question V4 run and a
per-case regression comparison.

### First V4 cohort attempt: harness failure, not hypothesis result

The first ten-case V4 cohort received ten API responses, but only one contained
complete valid JSON. Nine outputs ended while writing the first or a later
`quote_id`:

```text
API responses received       = 10 / 10
schema-valid responses       = 1 / 10
valid citation resolutions   = 1 / 10
```

The raw result and report are preserved as
`v4_failure_cohort_attempt1_results.jsonl` and
`v4_failure_cohort_attempt1_report.json`.

The one valid response proved deterministic quote resolution worked: all eight
selected quote IDs resolved to their exact source documents and excerpts. It
also exposed over-citation: the model selected eight quotes for one required
policy family.

This run does not accept or reject the V4 hypothesis because nine answers never
reached the scoring boundary. The harness was refined before another run:

- set an explicit 3,000-token output budget,
- treat incomplete API responses as retryable failures rather than successes,
- retain raw incomplete output and response details for diagnosis,
- require one strongest quote per policy family except for direct conflicts,
- increase quote spans from 220 to 320 characters so one policy sentence is not
  split into weak fragments.

The cohort must be rerun before the full 100-question comparison.

### Second V4 cohort attempt: constrained identifier failure

Attempt 2 correctly classified incomplete responses and retried them. Four of
ten cases completed; all four scored 100% for customer answers, family coverage,
quote resolution, exact excerpts, and unsupported-claim avoidance. Six cases
remained incomplete after three attempts:

```text
eventual completed responses = 4 / 10
first-attempt completions     = 2 / 10
schema validity when complete = 100%
reason for six failures       = max_output_tokens
```

Inspection showed every incomplete output stopped while selecting a long quote
identifier such as `KB-...::chunk-...::quote-...`. The model had already
generated the customer assessment and limitations. This indicated a structured
decoding bottleneck rather than ordinary prose verbosity.

The result and report are preserved as
`v4_failure_cohort_attempt2_results.jsonl` and
`v4_failure_cohort_attempt2_report.json`.

The deterministic resolver does not require a globally descriptive model-facing
identifier. Quote anchors were therefore changed to short context-local IDs:

```text
Q001 -> document ID + chunk ID + exact source text
Q002 -> document ID + chunk ID + exact source text
```

The response schema enumerates only the short IDs available in that request,
the application retains source identity, and policy sources are capped at six.
This keeps the fix inside the citation interface rather than changing retrieval
or raising the output budget until the constrained-decoding issue disappears.

### Third cohort attempt: V4 citation identity passes, coverage misses

Short quote IDs removed the completion failure. All ten cases completed on the
first attempt and produced valid structured outputs:

| Metric | V4 cohort result |
|---|---:|
| API success | 100% |
| Schema validity | 100% |
| Answer correctness | 100% |
| Citation resolution | 100% |
| Exact citation precision | 100% |
| Unsupported claims empty | 100% |
| Expected document citation | 80% |
| Expected family citation | 80% |

The result is preserved as `v4_failure_cohort_attempt3_results.jsonl` and
`v4_failure_cohort_attempt3_report.json`.

The two failures each had four required intents: retention, offers, consent, and
the `GAP-001` governance gap. The model used all six flat citation slots on
duplicate retention, offer, and consent quotes and omitted governance. A prompt
request for one quote per family did not make that constraint structural.

V4 therefore proves the quote-anchor hypothesis but fails the family-coverage
target. It is frozen at this result.

### V5 hypothesis: make intent coverage structural

V5 replaces the flat model citation list with required intent-keyed fields:

```text
I01 -> quote enum containing only retention sources
I02 -> quote enum containing only offer sources
I03 -> quote enum containing only consent sources
I04 -> quote enum containing only GAP-001 sources
```

Each intent permits one strongest quote and a second only for a direct policy
conflict. Application code still resolves short quote IDs to exact documents,
chunks, and excerpts.

The V5 hypothesis is:

> Required intent-keyed citation fields will raise document and family coverage
> from 80% to at least 90% while preserving 100% answer correctness and exact
> citation grounding.

This is a structured-output contract experiment. Retrieval, frozen labels,
Customer 360 inputs, model, reasoning setting, and context budget remain fixed.

### V5 cohort result: intent coverage passes, one claim overstates certainty

V5 made intent coverage structural. The ten-case cohort produced:

| Metric | V5 cohort result |
|---|---:|
| API and schema validity | 100% |
| Answer correctness | 100% |
| Expected document/family citation | 100% |
| Citation resolution and precision | 100% |
| Unsupported claims empty | 90% |

The single failure was `multiple_warning_signals_04__risk_investigation`. Its
summary changed the supported statement:

```text
causal benefit cannot be inferred
```

into the stronger statement:

```text
no causal benefit
```

`GAP-001` establishes missing causal evidence, not zero effect. The model
correctly placed its own overstatement in `unsupported_policy_claims`. The
metric therefore caught a real calibration failure and was not weakened.

V5 is frozen in `v5_failure_cohort_results.jsonl` and
`v5_failure_cohort_report.json`.

### V6 hypothesis: calibrate unknown versus zero effect

V6 adds one narrow prompt rule:

```text
unknown effect != no effect
not established != proven zero
```

It also requests a summary under 300 characters so a bounded field is less
likely to end with a malformed or compressed claim.

The V6 hypothesis is:

> Explicit causal-language calibration will remove the V5 unsupported claim
> while preserving 100% answer correctness, intent coverage, and exact citation
> grounding.

### V6 cohort result: all gates pass

V6 passed all ten targeted cases on the first API attempt:

| Metric | V6 cohort result |
|---|---:|
| API and schema validity | 100% |
| Answer correctness | 100% |
| Expected document/family citation | 100% |
| Citation resolution and precision | 100% |
| Unsupported claims empty | 100% |
| Reasoning tokens | 0 |

The previously failing causal summary now states only the observed risk and
investigation steps. It cites `GAP-001` without claiming either causal benefit
or zero effect. The summary is 234 characters and
`unsupported_policy_claims` is empty.

Across the cohort, the longest summary was 247 characters, policy citations
averaged 2.7 per response, and the maximum was five. The V5-to-V6 comparison
contains one improvement and zero regressions.

The targeted gate is complete. V6 is authorized for the frozen 100-question
adoption run; passing ten targeted cases is not itself the final Commit 07
result.

### Final 100-question V6 result

The live V6 retrieval gate passed all 100 questions. The full generation run
then produced:

| Metric | V6 result |
|---|---:|
| First-attempt API success | 100% |
| Schema validity | 100% |
| Risk and answer correctness | 100% |
| Expected document/family retrieval | 100% |
| Expected document/family citation | 100% |
| Citation resolution and exact precision | 100% |
| Unsupported claims empty | 100% |
| Reasoning tokens | 0 |
| Mean total latency | 5.5025 seconds |
| p95 total latency | 8.2808 seconds |
| Estimated generation cost | $0.637756 |

Both question types passed independently across 50 cases each. All 100 calls
completed on the first attempt, so retries did not hide instability.

### V3 versus V6 adoption comparison

The per-case comparison contains 100 shared cases and zero regressions for every
tracked metric.

Key improvements:

```text
API/schema/answer completion:      98 -> 100 cases
exact excerpt grounding:           82 -> 100 cases
expected policy documents cited:   90 -> 100 cases
expected policy families cited:    74 -> 100 cases
unsupported claims empty:          96 -> 100 cases
```

Mean total latency improved by 1.1919 seconds. Cost per successful response fell
from approximately `$0.007745` to `$0.006378`. Input tokens increased because
the dynamic intent schema carries more constraints, while output tokens fell
because summaries and citations became more focused.

### Manual audit and residual risk

The full results contained no duplicate quote IDs and no unexpected non-ASCII
text. Policy citations averaged 2.98 per answer with a maximum of five. One
summary was 304 characters despite the soft under-300 instruction; it remained
coherent and within the 500-character schema.

Exact excerpt grounding proves citation identity, not semantic entailment. Nine
policy-guardrail summaries without a governance intent say causal benefit is
"not established." This is a conservative uncertainty statement rather than a
claim of zero effect, but it would be more precise to say "the retrieved context
does not establish causal benefit." A future semantic citation evaluator should
measure that distinction rather than relying only on model self-report.

### Commit 07 conclusion

V6 is adopted. Commit 07 demonstrates a measured RAG pipeline in which retrieval,
customer-answer correctness, policy-intent coverage, exact citation identity,
unsupported claims, reliability, latency, tokens, and cost remain separately
observable.

It does not prove universal policy correctness, semantic entailment of every
sentence, production-scale reliability, or intervention effectiveness. It does
not add an agent or automatic execution. Those boundaries remain explicit.

---

## Commit 08 - Retrieval Experiments

### Learning objective

Commit 07 proved that the selected policy documents could support a grounded
answer. Commit 08 isolates the search system so that two failure classes remain
distinguishable:

```text
retrieval failure = required policy did not reach the model
generation failure = required policy arrived, but the model used it incorrectly
```

Changing a prompt cannot reliably repair the first failure class.

### Frozen experiment contract

The 50 Commit 06 retrieval cases and the generated knowledge corpus are pinned
by SHA-256 in `evals/commit08/experiment_contract.json`. The runner validates
both fingerprints before connecting to the embedding API or database.

The experiment changes one retrieval boundary at a time:

```text
metadata filtering
120/20, 220/0, 220/40, and 400/60 chunking
vector-only search
lexical reference
reciprocal-rank hybrid retrieval
lexical reranking of vector candidates
top K measured at 1, 3, 5, and 10
```

The four chunk configurations use isolated pgvector tables. The adopted Commit
07 index is not overwritten.

### Metric correction

Commit 06 defined `Recall@K` as the percentage of queries with at least one
relevant document in the first K results. That historical number is retained,
but Commit 08 names it `hit rate@K` because it is not the fraction of all
relevant documents recovered.

Commit 08 adds complete family/topic selector coverage. This matters for the
cross-family query: finding either campaign suppression or consent suppression
is an any-hit success, while the task requires both selectors.

### First local checkpoint

Frozen-input validation passes. The lexical-only reference requires no API and
reproduces the Commit 06 ranking result:

```text
hit rate@1  = 36%
hit rate@3  = 58%
hit rate@5  = 68%
hit rate@10 = 82%
MRR         = 0.4974
```

Complete selector coverage at rank 10 is 80%, two points below the any-hit
rate. The difference is the partial cross-family result, confirming that the
stronger metric detects a real retrieval omission.

### Full matrix result

| Experiment | Hit@5 | Selectors@5 | MRR | p95 ms | Decision |
|---|---:|---:|---:|---:|---|
| lexical reference | 68% | 68% | 0.4974 | 7.920 | reject: 15 regressions |
| vector unfiltered | 68% | 96% | 0.3908 | 33.407 | reject: governance |
| vector baseline | 98% | 96% | 0.9032 | 24.050 | retain |
| small chunks | 96% | 94% | 0.8944 | 24.625 | reject: one regression |
| no overlap | 98% | 96% | 0.9032 | 21.579 | equivalent treatment |
| large chunks | 96% | 94% | 0.8957 | 28.856 | reject: one regression |
| hybrid RRF | 88% | 86% | 0.7482 | 26.971 | reject: six regressions |
| lexical rerank | 94% | 92% | 0.9007 | 26.661 | reject: two regressions |

No distinct treatment strictly improved the baseline without introducing a
governance failure or a rank-five selector regression.

### Metadata is part of correctness

The unfiltered vector experiment had 96% selector coverage at rank five, but
only 26.4% of those results were both current and approved. Draft, superseded,
and reference documents deliberately share topics with authoritative policies.
The retrieval score cannot decide source authority; metadata filtering is a
hard correctness boundary.

### Empty treatment and avoidable cost

The `220/0` and `220/40` configurations produced byte-identical chunks and
embedding inputs:

```text
chunk count            = 1,093
embedding input tokens = 300,972
retrieval metrics      = identical
```

The corpus sections fit within the chunk budget, so overlap never executed.
The observed 2.471 ms p95 difference is run noise. Treatment fingerprints now
exclude this equivalent configuration from candidate selection.

This mistake consumed 300,972 duplicate embedding tokens. The broader lesson
is to compare effective model inputs before paying to run two nominally
different configurations.

Across all four index builds, the experiment used 1,228,865 embedding input
tokens and 64.066 seconds of build time. The query batch used 561 input tokens.

### Why global hybrid retrieval failed

Hybrid RRF improved `retention_02`: the relevant retention policy moved from
vector rank eight to fused rank four. But the same global rule caused six other
rank-five selector regressions. A local improvement does not justify a global
retriever change.

The lexical reranker caused two regressions and did not fix either persistent
baseline failure. Small and large chunks each caused one regression. These are
measured negative results, not configurations to tune until they appear better.

### Persistent failure classification

`retention_02` is a ranking ambiguity. The relevant policy is present at vector
rank eight, but semantically similar offer policies occupy the first five
positions.

`cross_family_01` is a query-decomposition failure. Every tested strategy covers
only one of two required policy selectors, even at rank ten. Increasing K,
changing chunks, or globally mixing rankings cannot recover an underrepresented
intent reliably.

The next retrieval hypothesis is explicit multi-intent decomposition. It must
be tested on a newly frozen multi-intent dataset rather than tuned against one
known failure. Commit 07 already uses deterministic policy-intent decomposition
for its bounded Customer 360 workflow and passed its 100-question retrieval
gate, so this remains a generalization backlog rather than a regression in the
adopted workflow.

### Commit 08 conclusion

The `vector_baseline` remains adopted. No new treatment earned an end-to-end
generation gate. Rerunning 100 LLM calls would test the existing pipeline again,
not a new retrieval hypothesis, so those calls were not spent.

The central learning is:

```text
retrieval experiments can correctly conclude "do not change the system"
```

Commit 08 is complete without adding agents or automatic execution.

---

## Commit 09 - CDP Tool Layer

### Objective

Commit 09 asks a narrower question than "can an agent use the CDP?":

> Can application capabilities be exposed as strict, deterministic APIs before
> a model is allowed to choose among them?

The order matters. A model can only call a tool safely when application code
owns validation, data access, error behavior, output shape, and side effects.
This commit therefore contains no model call and no agent loop.

### The seven contracts

The tool layer exposes seven normal Python functions through a registry:

| Tool | Deterministic responsibility |
|---|---|
| `get_customer_profile` | Return a bounded, PII-safe Customer 360 profile |
| `get_customer_events` | Return identity-resolved events within a validated lookback |
| `get_purchase_history` | Return bounded orders with product-line evidence |
| `search_knowledge_base` | Search current, approved knowledge documents |
| `calculate_customer_metrics` | Return existing semantic-layer metrics by domain |
| `get_campaign_eligibility` | Identify hard blocks or require further review |
| `create_retention_recommendation` | Construct a non-persisted draft with evidence |

Each contract has strict Pydantic input and output schemas. Unknown fields are
rejected. Identifiers, enums, limits, date windows, evidence counts, and
rationale length are validated before execution. Tool definitions expose their
JSON schemas and explicitly declare `side_effects = none`.

### Data boundaries are part of the contract

The tools do not expose arbitrary SQL or an unbounded data browser. Each one
owns a specific read path:

```text
customer profile     -> customer_360 without raw PII
event history        -> identity-resolved stg_events, 1-90 days, <=100 rows
purchase history     -> orders and lines, 1-730 days, <=50 orders
customer metrics     -> existing Customer 360 features, not a new score
knowledge search     -> current and approved documents only, <=10 results
campaign readiness   -> consent and status checks, no final eligibility claim
recommendation draft -> verified evidence values, no persistence or execution
```

Time windows use the semantic `customer_360.as_of_ts` rather than the machine
clock. That keeps repeated calls reproducible against a fixed warehouse.

The profile contract excludes raw email, phone, address, birth date, and
identity values. The model-facing layer receives only the attributes needed for
the bounded workflow.

### Honest names and outputs

The warehouse cannot prove final campaign eligibility. It does not contain the
specific campaign definition, audience rule, offer terms, or complete policy
interpretation. `get_campaign_eligibility` therefore returns only:

```text
BLOCKED
REVIEW_REQUIRED
```

It never returns `ELIGIBLE`. A contactable channel is permission to continue
reviewing, not permission to execute a campaign.

Likewise, `create_retention_recommendation` does not create a production
record. It returns a deterministic draft with:

```text
requires_human_approval = true
execution_allowed       = false
persisted               = false
```

Application code attaches the real Customer 360 evidence values and verifies
that referenced policy documents are current and approved. Authority checking
does not prove semantic entailment, so the output states that limitation.

### Search contract versus search implementation

The knowledge tool currently uses the deterministic local
`lexical_current_approved` adapter. This does not reverse the Commit 08 vector
retrieval decision. Commit 09 measures the API contract and execution behavior,
not retrieval quality. A vector implementation can replace the adapter behind
the same contract only after a retrieval and tool-level comparison.

This separation is important:

```text
tool interface       = stable application capability
retrieval algorithm  = replaceable implementation treatment
```

### Structured failure behavior

The registry turns execution outcomes into a stable envelope. Expected failures
do not leak stack traces or database details:

| Error | Meaning |
|---|---|
| `VALIDATION_ERROR` | Input violates the typed contract |
| `NOT_FOUND` | Customer or authoritative policy does not exist |
| `CONFLICT` | Request crosses a hard business boundary |
| `UNKNOWN_TOOL` | Requested tool is not registered |
| `INTERNAL_ERROR` | Unexpected execution failure |

SQL values are parameterized. Malformed IDs, excessive limits, unknown enum
values, extra arguments, unknown records, and conflicting recommendation
requests are all frozen evaluation cases.

### Frozen evaluation

The evaluation contains 105 cases:

```text
7 tools x 10 valid cases   = 70 valid cases
7 tools x 5 invalid cases  = 35 invalid cases
5 measured repetitions     = 525 executions
```

Every case is warmed once before measurement. Timings include validation,
bounded execution, output validation, and result-envelope construction. They
exclude one-time DuckDB connection and lexical-index construction.

| Tool | Valid success | Invalid behavior | p95 latency |
|---|---:|---:|---:|
| `calculate_customer_metrics` | 100% | 100% | 44.260 ms |
| `create_retention_recommendation` | 100% | 100% | 43.943 ms |
| `get_campaign_eligibility` | 100% | 100% | 44.134 ms |
| `get_customer_events` | 100% | 100% | 58.199 ms |
| `get_customer_profile` | 100% | 100% | 43.654 ms |
| `get_purchase_history` | 100% | 100% | 53.953 ms |
| `search_knowledge_base` | 100% | 100% | 4.596 ms |

Overall results:

```text
valid input success rate    = 100%
invalid input behavior rate = 100%
failed frozen cases         = 0
line/branch coverage         = 96.05%
coverage target              > 80%
```

The benchmark proves that the frozen calls satisfy their declared contracts
and that invalid inputs fail as expected. It does not prove that the tools are
complete for every business workflow, that lexical retrieval is best, or that
a model will select the correct tool and arguments.

### Lessons

1. A tool is an API endpoint whose caller may be probabilistic. That makes the
   deterministic contract more important, not less important.
2. The model should choose intent; application code must own authority,
   validation, bounded access, and side effects.
3. Useful refusal states such as `REVIEW_REQUIRED` are more honest than false
   precision.
4. A function named `create` is dangerous unless persistence and execution are
   explicit contract fields.
5. Valid-path tests are insufficient. An agent-facing API needs measured
   invalid-input behavior because malformed calls are normal operating events.
6. Tool quality and model tool-selection quality are separate evaluation
   problems.

### Commit 09 conclusion

The CDP now has a typed, read-only capability layer that can be offered to a
model without exposing the warehouse directly. Commit 10 can introduce the
first bounded agent and measure whether the model chooses the right tool,
constructs valid arguments, and stops correctly. Automatic customer action
remains out of scope.

---

## Commit 10 - Single-Agent Customer Investigator

### Objective

Commit 10 asks whether one model can control a bounded investigation loop over
the deterministic Commit 09 tools:

> Can the model select the right read-only capabilities, construct valid
> arguments, use returned evidence, and stop with a grounded answer without
> receiving database access or execution authority?

This is the first agent in SignalDesk. It is implemented directly with the
Responses API so the primitive loop remains visible:

```text
question
  -> model selects a tool
  -> application validates subject and arguments
  -> deterministic tool executes
  -> result returns to the model
  -> model calls another tool or returns a typed answer
```

The model receives six read-only tools. The recommendation-draft tool is not
exposed, and no capability can contact a customer, execute a campaign, persist
a recommendation, or modify the warehouse.

### Application ownership did not change

The model chooses intent. Application code still owns the tool allowlist,
customer subject binding, argument validation, deterministic execution, round
and call limits, retries, and final schema validation.

Calls for a customer other than the task subject fail before tool execution.
Tool outputs are untrusted data. The transcript uses `store=False`, and the
application explicitly carries tool calls and outputs between model rounds.

### Frozen evaluation

The 50-task suite uses 50 distinct customers from the clean Commit 05 cohort:

| Task type | Cases | Required tools |
|---|---:|---|
| Multi-signal investigation | 10 | Metrics, purchases, events |
| Purchase investigation | 10 | Metrics, purchases |
| Behavior investigation | 10 | Metrics, events |
| Support-policy investigation | 10 | Metrics, support knowledge |
| Profile lookup | 5 | Profile |
| Campaign readiness | 5 | Eligibility, campaign policy, consent policy |

The model and reasoning boundary remained fixed:

```text
model     = gpt-5.6-luna
reasoning = none
```

Correct tool selection, argument validity, unnecessary calls, conclusion,
summary completion, scalar grounding, required evidence, policy retrieval,
policy citation evidence, policy-family coverage, and task completion are
measured separately. Efficiency is not hidden inside correctness.

### Prompt versions were hypotheses

V1 established the primitive loop in a six-case pilot and exposed an evaluator
bug: precise dotted evidence paths were being flattened incorrectly.

V2 corrected canonical paths, decomposed multi-family policy search, and
bounded summaries. Its full run selected correct tools and arguments and
reached correct conclusions on every task, but required evidence reached 86%
and completion reached 80% under the historical rubric.

Trace review found four causes:

```text
7 answers filled all 10 evidence slots and omitted the decisive flag
6 answers treated a successful bounded event sample as an incomplete task
2 support tasks made an unnecessary profile lookup
policy citations proved retrieval membership, not evidence use
```

V3 prioritized conclusion-defining flags, clarified bounded truncation,
restricted profile lookups to profile questions, and required cited policy IDs
plus exact excerpts. It completed 20 of 25 diagnostic cases. All remaining
failures were campaign tasks where channel details consumed the evidence
budget.

V4 changed only that allocation. Campaign answers reserve five slots for the
overall status and one ID/excerpt pair from each required policy family. At most
two channel details may follow. The five campaign cases passed before the
accepted prompt was run over all 50 tasks.

### Final measured result

V2 was regraded in memory with the stricter V4 evaluator so both prompt
versions use the same completion definition:

| Metric | V2 regraded | V4 full |
|---|---:|---:|
| API success | 100% | 100% |
| Correct tools | 100% | 100% |
| Correct arguments | 100% | 100% |
| Unnecessary-tools empty | 96% | 98% |
| Correct conclusion | 100% | 100% |
| Required evidence present | 86% | 100% |
| Policy citations evidenced | 70% | 100% |
| Policy-task completion | 0% | 100% |
| Overall task completion | 50% | 100% |

The original V2 report remains preserved at 80% completion because its
evaluator did not yet require exact citation evidence. Preserving both numbers
makes the metric change visible.

V4 operational measurements:

```text
mean / p50 / p95 latency = 6.0616 / 5.4742 / 9.2174 seconds
tool calls                = 111 total, 2.22 mean/task
API requests              = 106
retry attempts            = 0
input / output tokens     = 302,870 / 22,966
estimated cost            = $0.236846 total, $0.00473691/task
```

Compared with V2, V4 reduced mean latency by 12%, p95 latency by 31%, output
tokens by 17%, and estimated cost by 8%. Input tokens increased by 24% because
the accepted prompt carries more explicit constraints.

One purchase task repeated `calculate_customer_metrics` with identical
arguments. The evaluator exposed the only efficiency miss. It did not affect
correctness, and another prompt version for one probabilistic duplicate would
overfit the frozen suite.

### What the result does not prove

Exact policy citation evidence proves that IDs and excerpts came from
retrieved, current, approved documents in the required families. It does not
prove that the excerpt is the most semantically specific support. Seventeen of
20 cited excerpts used the same generic uncertainty and escalation passage.

The frozen cases also became the development regression suite for V3 and V4.
The 100% completion result proves conformance to that contract, not 100%
accuracy on unseen questions. There is no holdout, repeated stochastic run,
write-capable tool, human approval workflow, or production action in this
commit.

### Commit 10 conclusion

The first bounded agent can select deterministic CDP tools, respect subject and
argument boundaries, collect evidence, and terminate with a typed grounded
answer over the frozen suite. The important lesson is not the 100% headline.
It is that aggregate correctness hid evidence allocation, completion semantics,
citation grounding, and unnecessary calls until those behaviors were measured
independently.

V4 is accepted. Commit 11 can introduce explicit workflow state and framework
orchestration without changing the underlying rule:

```text
model proposes
application validates and executes
evaluation decides whether behavior earned adoption
```

## Commit 11 - From an Agent Loop to a Stateful Workflow

Commit 11 asks whether explicit orchestration adds useful control without
changing the accepted agent behavior.

The treatment is intentionally narrow:

```text
fixed                              changed
-----                              -------
gpt-5.6-luna                       manual loop -> LangGraph StateGraph
reasoning = none                   local variables -> typed graph state
Commit 10 V4 prompt                implicit branches -> named routes
six read-only tools                no checkpoints -> per-node checkpoints
50 frozen customers                restart -> resume from failed node
answer schema and evaluator
```

### The loop already had state

Commit 10 carried the request, Responses API transcript, pending function
calls, tool traces, usage totals, and final answer in Python variables. That was
state even though it was not named as a state machine.

LangGraph does not create intelligence. It makes those variables a contract
shared by explicit nodes:

```text
interpret_request
resolve_customer
investigation_router
profile | events | knowledge | reason_about_case
recommend_action
approval_required
finish
```

The model still decides which tool to request. Application code maps that
approved tool to a deterministic route, validates its arguments, binds it to
the task customer, executes it, and records the transition.

### Checkpoints change failure semantics

The graph compiles with an `InMemorySaver`. Every successful graph step creates
a checkpoint keyed by a thread ID. If `reason_about_case` fails, the stored
snapshot still identifies that node as the next step. Calling
`resume(thread_id)` retries from there instead of repeating request
interpretation and customer resolution.

This is process-local learning infrastructure, not durable production
persistence. A process restart loses the checkpoints. Commit 11 demonstrates
the contract before choosing a durable store.

### The action path is visible but closed

The roadmap's graph includes recommendation, approval, and action execution,
but Commit 12 owns human approval and consequential tools. Commit 11 therefore
records:

```text
recommendation    = ANALYSIS_ONLY
approval_required = false
action_executed   = false
```

The action node raises if reached. Modeling a future edge does not grant the
system future authority.

### Quantifiable workflow experiment

The 50 accepted Commit 10 runs produce 100 frozen workflow scenarios:

```text
50 standard replays
50 replays with one injected reasoning-node failure followed by resume
```

Measured result:

```text
completion                 100%
correct routing            100%
tool-count agreement       100%
rubric task completion     100%
checkpoint recovery        100%
average tool calls         2.22
failed executions          0
approval-required paths    0
actions executed           0
```

Completed workflows wrote 14 to 18 checkpoints, with a mean of 16.44.

This is a deterministic replay experiment. It proves that the graph can
reproduce accepted tool traces, preserve the rubric result, and recover from a
known injected node failure. It does not prove that a new stochastic model run
will make identical decisions.

### Live 50-case comparison

The second experiment ran the same frozen customers through the LangGraph
workflow. These variables remained fixed:

```text
model             gpt-5.6-luna
reasoning          none
prompt             commit10_v4_campaign_evidence_budget
tools              six read-only Commit 09 tools
cases              50 frozen Commit 10 tasks
answer schema      InvestigationAnswer
evaluator          Commit 10 V4 rubric
```

Only orchestration changed from the manual loop to the state graph.

| Metric | Commit 10 loop | Commit 11 LangGraph |
|---|---:|---:|
| API success | 100% | 100% |
| Correct tools | 100% | 100% |
| Correct arguments | 100% | 100% |
| Unnecessary-tools empty | 98% | 100% |
| Correct conclusions | 100% | 100% |
| Required evidence | 100% | 100% |
| Policy citations evidenced | 100% | 100% |
| Task completion | 100% | 100% |
| Correct graph routing | not applicable | 100% |

The comparison found no task-completion regressions, no routing failures, no
approval-required paths, and no executed actions.

Operational measurements:

| Measurement | Commit 10 loop | Commit 11 LangGraph |
|---|---:|---:|
| Mean / p50 / p95 latency | 6.0616 / 5.4742 / 9.2174s | 5.4044 / 5.0890 / 7.7938s |
| Tool calls | 111 | 110 |
| API requests | 106 | 103 |
| Input tokens | 302,870 | 293,566 |
| Output tokens | 22,966 | 22,730 |
| Estimated cost | $0.236846 | $0.233834 |

The candidate wrote 826 checkpoints, averaging 16.52 per task. Forty-seven
tasks completed in two model rounds and three completed in three rounds. No
tool execution failed and no API retry was needed.

The Commit 10 duplicate metrics call in `agent_purchase_decline_only_08` did
not recur. Two engagement cases also used one fewer model round. These are
observed stochastic differences, not evidence that LangGraph made the model
more efficient. The graph preserved the request contract; it did not change
the prompt hypothesis.

### What Commit 11 does not prove

Seventeen of 20 cited policy excerpts still use the same generic uncertainty
and escalation passage. Provenance, exact citation evidence, and family
coverage pass; semantic specificity remains a separate retrieval and corpus
limitation.

The 100-scenario replay proves recovery from one injected node failure. The
live run had no failures, so it did not exercise live resume behavior. The
checkpointer is also process-local and not durable across restarts.

The 50 cases are a development regression suite, not a holdout. One live run
does not estimate stochastic variance or production reliability. Commit 11 has
no write-capable tool, human approval, or production action.

### Commit 11 conclusion

Commit 11 V1 is accepted.

> Explicit LangGraph state, routing, checkpoints, and resume semantics
> preserved the accepted agent behavior without introducing regressions.

The framework earned adoption for orchestration and observability, not for an
unmeasured claim of greater intelligence. Commit 12 can now introduce a real
human approval boundary and consequential action tools on top of a measured,
read-only state machine.

## Commit 12 - Human Approval and Consequential Synthetic Actions

Commit 12 asks whether SignalDesk can add write-capable synthetic actions
without giving the model direct execution authority.

The application supports five typed proposals:

```text
issue coupon
enroll campaign
create support case
flag account
send retention offer
```

The model-facing investigation remains `gpt-5.6-luna` with reasoning set to
`none`. The authorization experiment makes no model calls. It freezes action
proposals so the treatment measures permission and recovery mechanics rather
than recommendation quality.

### Recommendation is not authorization

The workflow separates four stages:

```text
investigate -> recommend -> human decision -> execute exact payload
```

Every proposal has an immutable action ID derived from its customer, typed
payload, recommendation, reason, expected impact, source case, and proposer.
Changing any reviewed field invalidates the ID. A decision for another action
is rejected, and a completed thread cannot receive a second decision.

### Durable interruption

The graph records the proposal and approval request, then pauses with a
LangGraph `interrupt`. Its SQLite checkpointer survives closing and reopening
the workflow. Resume requires the same thread ID and a typed approve or reject
decision.

Checkpoint state and action history are stored separately:

```text
checkpoints.sqlite3   where graph execution should resume
actions.sqlite3       proposal, decision, audit, synthetic CDP event
```

The source customer warehouse remains read-only.

### Why execution is idempotent

An approved event may commit immediately before the process fails. The graph's
last checkpoint then says to execute again. The action ID is therefore a unique
key in the synthetic event ledger, and audit rows are unique by action and
event type. A retry returns the existing event instead of writing a duplicate.

### Frozen experiment

All 50 accepted Commit 10 customer cases are reused. Each has one approved and
one rejected proposal, producing 100 cases. The five action types have 20 cases
each. Twenty-five approved paths inject a failure after the event commits and
then recover using a fresh workflow instance.

Measured result:

```text
approval gated                         100%
correct approve/reject outcome         100%
fully audited                          100%
post-commit recovery                    100% (25/25)
approved actions executed once         100%
rejected actions not executed          100%
duplicate-action rate                    0%
```

### What this does not prove

This is a local learning system. Reviewer identity is not authenticated,
SQLite is not a managed authorization service, audit rows are not tamper-proof,
and actions write only synthetic events. There are no real coupon, campaign,
support, account, or messaging integrations.

The benchmark also does not evaluate whether each action is the best business
recommendation for its customer. A separate recommendation-quality experiment
would need curated expected actions, holdout cases, and repeated model runs.

### Commit 12 conclusion

Commit 12 V1 is accepted.

> The durable workflow enforced approval before every consequential synthetic
> action, preserved a complete decision audit, recovered after interruption,
> and produced no duplicate events across the frozen 100-case benchmark.

The key lesson is that permission is an application concern. The model may
propose; only a validated human decision can grant authority to execute the
exact reviewed payload.

## Commit 13 - Comparing LangGraph and the OpenAI Agents SDK

Commit 13 asks whether the approval architecture learned in Commit 12 can be
implemented in another runtime without weakening its behavior.

The experiment freezes one small workflow:

```text
model proposes ISSUE_COUPON
-> human approval interruption
-> approve or reject
-> synthetic event or no event
-> audit and recovery
```

Twenty frozen Commit 12 coupon cases contain ten approvals, ten rejections, and
five approved paths with a failure after the event commits.

### Runtime A: LangGraph

LangGraph represents the process as typed state, named nodes, conditional
edges, SQLite checkpoints, `interrupt`, and `Command` resume. The application
owns the action node.

### Runtime B: OpenAI Agents SDK

The SDK represents the process as an agent loop with an `issue_coupon` function
tool marked `needs_approval=True`. A model tool call produces an interruption.
The application serializes `RunState`, reconstructs it after restart, records
the decision, approves or rejects the specific tool call, and resumes the
runner.

The SDK owns approval state for the tool call. The application still owns exact
payload validation, the reviewer audit, and idempotent execution.

### Controlled model replay

The candidate defaults to `gpt-5.6-luna` with reasoning `none`, but the measured
comparison replaces the network model with a deterministic SDK `Model`. It
emits the frozen tool call and final answer through the real runner.

This produced 40 runtime executions and 40 deterministic replay calls with no
external model API calls. The claim is orchestration parity, not new model
quality.

### Result

```text
                                      LangGraph   Agents SDK
approval gated                          100%         100%
correct outcome                         100%         100%
fully audited                           100%         100%
recovery                                100%         100%
duplicate-action rate                     0%           0%
mean local runtime                    26.6771ms     19.4219ms
p95 local runtime                     35.2724ms     26.6900ms
mean pending-state artifact          28,672B        8,285B
```

Both runtimes satisfy the frozen behavior contract. An adversarial test changes
the model-proposed discount from 10% to 50%; the SDK adapter rejects it before
review or execution.

### Interpretation limits

The local latency excludes network model time and is not a production
performance result. State size compares SQLite file allocation with JSON
payload length. Source size also reflects different integration choices and is
not a quality score.

Behavioral parity is the defensible conclusion.

### Dependency finding

`openai-agents==0.18.3` requires `openai>=2.45,<3`. Installation resolved the
OpenAI client from `3.2.0` to `2.54.0`. All SignalDesk tests passed under the
resolved environment, but a framework changing a shared foundational
dependency is architecture evidence, not installation trivia.

### Framework decision

SignalDesk retains LangGraph.

Its workflow is an explicit long-running business state machine with visible
investigation routes, approval, execution, and recovery boundaries. Named
nodes and checkpoint snapshots fit that shape.

The OpenAI Agents SDK is a viable alternative and passed the same permission
contract. It fits naturally when the central abstraction is a model/tool loop
and native approvals, sessions, handoffs, and tracing matter more than explicit
domain graph transitions.

### Commit 13 conclusion

> Framework selection should follow workflow shape, persistence ownership,
> operational constraints, and customer environment rather than framework
> popularity.

Commit 13 proves that the safety architecture is portable across runtimes. The
decision to retain LangGraph is contextual, not an expression of framework
loyalty.

## Commit 14 - Turning the CDP Into an MCP Server

Commit 14 asks whether selected SignalDesk capabilities can cross a standardized
integration boundary without weakening their internal contracts.

### Starting point

Commit 09 already provided seven deterministic Python tools. Their contracts
include strict Pydantic schemas, typed outputs, read-only DuckDB access, bounded
queries, PII-safe profiles, approved knowledge filters, and structured errors.

The MCP milestone did not need new CDP logic. It needed a protocol adapter.

### Published capability set

The server exposes exactly four roadmap tools:

```text
customer_profile
customer_events
knowledge_search
campaign_eligibility
```

Each maps to the existing `ToolRegistry`. No recommendation, approval, or action
tool is exposed. Capability selection is part of authorization; an internal
function does not become externally available by default.

### Protocol and transport

The implementation uses the MCP Python SDK `1.29.0` with stateless Streamable
HTTP and JSON responses.

Clients can:

```text
initialize
discover tools
inspect input/output schemas
invoke a named tool
receive structured content
```

All four tools publish read-only, non-destructive, idempotent, closed-world
annotations. Their flat schemas reject extra fields and preserve the existing
customer ID, event-window, result-limit, family, and channel constraints.

### Authentication boundary

Every MCP request requires a pre-issued bearer token with the
`signaldesk:read` scope. The server uses the SDK `TokenVerifier` and publishes
protected-resource metadata.

The local token is supplied only through `SIGNALDESK_MCP_TOKEN` and compared as
a SHA-256 digest. This exercises authentication at the resource boundary but is
not a complete OAuth system.

### Error taxonomy

The experiment made two error layers visible:

```text
malformed or schema-invalid call -> MCP isError=true
valid call with missing customer -> ToolCallResult success=false / NOT_FOUND
```

The first is a protocol contract failure. The second is a domain outcome. This
distinction helps clients decide whether to repair a request or handle an
expected business condition.

### Measured result

```text
MCP tools                         4
strict schemas                    4/4
bearer authentication             enforced
integration tests                 27/27 passed
full repository tests             109/109 passed
external model API calls          0
write-capable MCP tools            0
```

A separate server and MCP client also completed initialization, discovery, and
an authenticated `customer_profile` call over localhost HTTP. The result
preserved `pii_included=false` and contained no email or phone field.

### What MCP owns

MCP owns the reusable conversation between client and server:

```text
discovery + schemas + invocation + structured result transport
```

SignalDesk still owns:

```text
authorization policy
tool allow-list
data semantics
query bounds
PII boundary
knowledge authority
domain errors
```

MCP is an integration protocol, not an agent, authorization policy, or business
logic framework.

### Limitations

This is a local learning resource server. It has no token-issuing authorization
server, TLS, short-lived identities, rotation, revocation, tenant isolation,
rate limiting, deployment configuration, or production concurrency design.

No model was called. `gpt-5.6-luna` with reasoning `none` remains the accepted
configuration for model-driven SignalDesk workflows, but MCP transport tests
are deterministic and independent of model quality.

### Commit 14 conclusion

> Standardizing tool access is valuable only when the exported capability set,
> schemas, authentication, and domain boundaries remain explicit and tested.

Commit 14 converts trusted internal CDP capabilities into a narrow integration
product without duplicating or expanding their authority.

## Commit 15 - Production API and UI

Commit 15 asks whether the accepted SignalDesk components can support the
original analyst journey through a coherent product boundary.

### Starting point

The repository already had Customer 360, evaluated generation and retrieval,
typed tools, a bounded agent, LangGraph orchestration, durable human approval,
and an MCP integration. Those components were accessible through Python entry
points and JSON reports rather than an analyst workspace.

### Product surface

The milestone adds a FastAPI service and Next.js workspace with:

```text
authenticated local session
warning-first customer search
PII-safe Customer 360
investigation conversation
grounded evidence
retrieved policy sources
executed tool summaries
LangGraph timeline
exact-payload approval prompt
```

The product layer reuses the existing `ToolRegistry`, accepted
`LangGraphCustomerInvestigator`, and `HumanApprovalWorkflow`. It does not create
a second implementation of customer metrics, retrieval, or approval semantics.

### Boundary decisions

The browser receives explicit Pydantic API views rather than internal model SDK
or graph state. Signed HttpOnly cookies authenticate sessions, CSRF tokens
protect writes, CORS is allow-listed, and SQLite records are scoped to the
signed user ID.

This is a local authentication pattern for learning. It is not production SSO,
tenant authorization, session revocation, TLS, or managed secrets.

### Action semantics

The workspace can draft a synthetic support-case follow-up after an
investigation. Its provenance is `signaldesk_workspace`, not
`signaldesk_agent`. The analyst reviews the exact payload before Commit 12's
durable workflow can execute one synthetic event.

This avoids an unsupported claim that the agent learned action selection.

### Verification

```text
Commit 15 API tests                    18 passed
full repository tests                 127 passed
Python lint                            passed
OpenAPI paths                          8
frontend type-check                    passed
frontend lint                          passed
frontend production build             passed
desktop browser workflow              passed
390px mobile layout                    passed
model                                  gpt-5.6-luna
reasoning effort                       none
accepted prompt                        commit10_v4_campaign_evidence_budget
human workflow target                  not measured yet
```

The backend tests cover authentication, signed-session integrity, expiry,
CSRF, customer search, PII exclusion, investigation shaping and ownership,
approval, rejection, and duplicate-decision conflict behavior.

Browser verification used the real API for authentication, search, Customer
360, and clean investigation failure handling. The frozen test investigator
then exercised the full evidence, source, tool, timeline, and exact-payload
approval views without an external model call. Desktop and 390px mobile checks
had no document overflow; the approval payload wrapped without horizontal
scrolling. One approved synthetic action reached `EXECUTED`.

### Metric discipline

The roadmap target is 20-30 minutes to less than three minutes per customer.
Agent latency cannot establish it. A timed user study must start when an analyst
opens a customer and stop after evidence review and decision. Median, p95, and
the percentage under three minutes should be reported separately from API
latency.

### Scope boundary

Commit 15 stores only enough local state to reload owned investigations and tie
approvals to them. Complete request tracing, evaluation joins, cost dashboards,
and error telemetry remain Commit 16. Deployment and reliability remain Commit
17.

### Commit 15 conclusion

> Productization means arranging trusted capabilities around a user's decision,
> enforcing the browser/API boundary, and measuring the human workflow rather
> than merely wrapping a model call in a screen.
