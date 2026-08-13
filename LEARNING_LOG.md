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
