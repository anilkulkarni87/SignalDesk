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
