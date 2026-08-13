# SignalDesk Architecture V0

## 1. Architecture Goals

SignalDesk V1 should support NovaCart's customer-retention investigation workflow without replacing the existing at-risk identification process.

The architecture should:

- Help Retention Specialists investigate customers identified as at risk.
- Gather relevant customer evidence from deterministic data sources.
- Present a concise view of customer behavior and important signals.
- Recommend one of the allowed interventions:
  - No action
  - Retention offer
  - Escalate to Support
- Show the evidence supporting a recommendation.
- Preserve meaningful human review before consequential actions are taken.
- Provide Retention Managers with a separate analytics surface for monitoring investigation performance.
- Keep operational customer investigation separate from aggregate management analytics.
- Allow customer facts and business knowledge to evolve independently.
- Create clear boundaries between investigation, recommendation, approval, and execution.

## 2. System Context

SignalDesk serves three primary personas.

### Retention Specialist

Uses the operational investigation experience to:

1. Select or receive an at-risk customer.
2. Review assembled customer evidence.
3. Understand important changes in customer behavior.
4. Review a proposed intervention.
5. Approve, modify, or reject the recommendation.

### Retention Manager

Uses a separate analytics experience to monitor:

- Investigation coverage
- Investigation efficiency
- Intervention distribution
- Retention offer volume
- Support escalation volume
- Recommendation overrides or disagreements
- Available outcome metrics

The Retention Manager does not primarily investigate individual customers.

### Customer Support Specialist

Receives context-rich escalations when a Retention Specialist determines that a customer problem requires Support involvement.

The support handoff should include enough evidence to avoid repeating the entire customer investigation.

## 3. Core Components

### 3.1 Retention Investigation UI

Primary user: Retention Specialist.

Responsibilities:

- Display the at-risk customer being investigated.
- Show relevant customer evidence.
- Show behavioral changes and important signals.
- Display the proposed intervention.
- Show evidence supporting the recommendation.
- Allow the specialist to approve, modify, or reject the recommendation.
- Capture the final decision and available rationale.

This is an operational interface focused on one customer at a time.

### 3.2 Retention Analytics Surface

Primary user: Retention Manager.

Responsibilities:

- Show weekly at-risk population size.
- Show investigation coverage.
- Show investigation-time metrics.
- Show intervention distribution.
- Show retention-offer and support-escalation volumes.
- Show recommendation override or disagreement rates.
- Show available workflow-quality and outcome metrics.

This is an aggregate analytical interface rather than a customer investigation interface.

### 3.3 Application API

Responsibilities:

- Provide application capabilities to the investigation and analytics surfaces.
- Coordinate customer investigation requests.
- Retrieve required customer evidence.
- Apply deterministic business rules where appropriate.
- Produce the information required for an intervention recommendation.
- Record investigation and decision outcomes.
- Provide aggregated workflow metrics for management reporting.

The Application API is a logical responsibility in V0. A specific implementation technology is not selected yet.

### 3.4 Customer Data Access Layer

Responsibilities:

- Provide controlled access to deterministic customer facts.
- Hide underlying storage complexity from application logic.
- Expose consistent customer-level data contracts.

Examples of customer facts include:

- Purchase history
- Order history
- Purchase frequency and recency
- Behavioral engagement
- Cart activity
- Email engagement
- Support history
- Customer attributes
- Consent information
- Offer eligibility inputs

Customer facts should come from authoritative structured data rather than being inferred when they can be calculated deterministically.

### 3.5 Customer Data Store / CDP

Responsibilities:

Store the structured customer and behavioral data required for investigation.

Expected data domains include:

- Customers
- Identities
- Sessions
- Behavioral events
- Orders
- Order items
- Campaign interactions
- Support tickets
- Consent preferences

The existing at-risk model is upstream of SignalDesk and provides the candidate customer population.

### 3.6 Business Rules

Responsibilities:

Represent rules that should remain deterministic.

Examples may include:

- Retention offer eligibility
- Consent restrictions
- Intervention constraints
- Customer-status restrictions
- Operational policies that can be represented as explicit rules

A recommendation must not override deterministic eligibility or consent restrictions.

### 3.7 Business Knowledge

Responsibilities:

Provide informational context that may help explain or determine an appropriate intervention.

Examples include:

- Retention playbooks
- Support procedures
- Campaign guidelines
- Policy explanations
- Customer-service guidance

Business knowledge is logically separate from structured customer facts.

V0 does not yet prescribe how this knowledge will be searched or retrieved.

### 3.8 Investigation and Decision Records

Responsibilities:

Capture the outcome of every investigation.

A record should eventually contain information such as:

- Customer identifier
- Investigation timestamp
- Evidence considered
- Investigation summary
- Proposed intervention
- Final human decision
- Whether the recommendation was accepted, modified, or rejected
- Available rationale
- Support escalation status where applicable

These records provide the foundation for auditability and management analytics.

## 4. Data and Decision Flow

### Customer Investigation Flow

```text
Existing At-Risk Model
        |
        v
Weekly At-Risk Customer Population
        |
        v
Retention Investigation UI
        |
        v
Application API
        |
        +--------------------------+
        |                          |
        v                          v
Customer Data Access         Business Knowledge
        |                          |
        v                          v
Customer / CDP Data          Policies / Playbooks
        |
        v
Deterministic Business Rules
        |
        v
Customer Evidence
        |
        v
Investigation Summary
        |
        v
Proposed Intervention
        |
        v
Supporting Evidence
        |
        v
Retention Specialist Review
        |
        +------------+-------------+
        |            |             |
        v            v             v
    Approve        Modify        Reject
        \            |             /
         +-----------+------------+
                     |
                     v
               Final Decision
                     |
                     v
          Investigation Record
```

### Management Analytics Flow

```text
Investigation Records
        +
At-Risk Population
        +
Workflow Metrics
        |
        v
Analytics / Aggregation Layer
        |
        v
Retention Analytics Surface
        |
        v
Retention Manager
```

### Support Escalation Flow

```text
Final Decision
        |
        v
ESCALATE_TO_SUPPORT
        |
        v
Context-Rich Handoff
        |
        v
Customer Support Specialist
        |
        v
Support Resolution
```

### Important separation

```text
Customer facts
    ↓
deterministic data access

Business knowledge
    ↓
knowledge-access capability

Recommendation
    ↓
decision-support capability

Execution
    ↓
separate controlled action
```

These responsibilities should not be collapsed into one component.

## 5. Architectural Boundaries

### Existing at-risk model remains upstream

SignalDesk does not replace the existing at-risk model in V1.

The existing system answers:

"Which customers should be investigated?"

SignalDesk addresses:

"What is happening with this customer, and what intervention should we consider?"

### Recommendation is separate from execution

SignalDesk may produce a recommendation.

A recommendation must not automatically cause a consequential customer action.

The V1 flow is:

```text
Investigation
→ Recommendation
→ Evidence
→ Human Review
→ Final Decision
```

Not:

```text
Investigation
→ Recommendation
→ Automatic Execution
```

### Customer facts must remain deterministic where possible

Values such as:

- Number of orders
- Days since last purchase
- Support-ticket count
- Purchase-frequency change
- Offer eligibility

should be calculated or retrieved from authoritative data sources.

They should not be invented or estimated when deterministic data is available.

### Business rules remain deterministic

Eligibility, consent, and similar hard constraints should remain explicit rules.

A recommendation cannot override those constraints.

### Evidence must accompany recommendations

A Retention Specialist should be able to determine why a recommendation was made.

A recommendation without inspectable supporting evidence does not satisfy the V1 product requirements.

### Management analytics is a separate user experience

The Retention Manager should have a dedicated analytics surface rather than using the Retention Specialist's investigation workflow as a reporting tool.

Both surfaces should reuse common underlying customer data, investigation records, and metrics rather than creating independent sources of truth.

### V1 does not optimize incentive values

SignalDesk may recommend an existing retention offer when appropriate.

Determining the optimal discount amount or estimating individual treatment effect is outside V1 scope.

### V1 does not claim causal business impact

SignalDesk can measure workflow performance and evaluation-set decision quality.

Claims such as:

"SignalDesk increased customer retention by 12%"

require an appropriate real-world experimental design and cannot be established from synthetic evaluation data alone.

## 6. Architecture V0 Diagram

```text
                         +----------------------+
                         | Existing At-Risk     |
                         | Model                |
                         +----------+-----------+
                                    |
                                    v
                          At-Risk Population
                                    |
                                    v
                 +------------------+------------------+
                 |                                     |
                 v                                     v
      +----------------------+              +----------------------+
      | Retention Specialist |              | Retention Manager    |
      | Investigation UI     |              | Analytics Surface    |
      +----------+-----------+              +----------+-----------+
                 |                                     |
                 v                                     |
           +-----------------------------------------------+
           |              Application API                  |
           +---------+------------------+------------------+
                     |                  |              ^
                     v                  v              |
          +------------------+   +-------------+       |
          | Customer Data    |   | Business    |       |
          | Access Layer     |   | Knowledge   |       |
          +--------+---------+   +-------------+       |
                   |                                  |
                   v                                  |
          +------------------+                        |
          | Customer / CDP   |                        |
          | Data             |                        |
          +--------+---------+                        |
                   |                                  |
                   v                                  |
          +------------------+                        |
          | Business Rules   |                        |
          +--------+---------+                        |
                   |                                  |
                   v                                  |
          Investigation + Recommendation              |
                   |                                  |
                   v                                  |
          +------------------+                        |
          | Human Review     |                        |
          +--------+---------+                        |
                   |                                  |
                   v                                  |
          +------------------+                        |
          | Investigation &  +------------------------+
          | Decision Records |
          +--------+---------+
                   |
          if support escalation
                   |
                   v
          +------------------+
          | Customer Support |
          | Specialist       |
          +------------------+
```

## 7. V0 Technology Position

Architecture V0 deliberately does not select technologies for capabilities that have not yet been validated.

At this stage the architecture does not require:

- A specific application framework
- An agent framework
- A vector database
- Embeddings
- A graph-based orchestration system
- A standardized tool protocol
- A multi-agent architecture

Those technologies should be introduced later only when a demonstrated requirement justifies them.
