# NovaCart Discovery Notes

## Discovery Objective

Understand the current customer-retention investigation workflow, identify the primary users and decisions involved, and define the workflows SignalDesk should improve in V1.

The current discovery indicates that NovaCart already has an upstream model that produces approximately 2,000 at-risk customers each week. The main constraint is the team's ability to investigate those customers and make informed intervention decisions at scale.

---

## Persona 1 — Retention Specialist

**Role:** Retention Specialist

**Primary goal:** Investigate customers identified as at risk and determine whether an intervention is appropriate.

**Trigger:** A weekly at-risk customer list provided by the existing at-risk model.

**Information needed:**
- Customer purchase history
- Purchase frequency and recency
- Order details
- Behavioral engagement
- Cart activity
- Email engagement
- Support history
- Relevant offer eligibility or retention rules

**Decision:** Choose among:
- No action
- Retention offer
- Escalate to Support

**Pain:** The team does not have enough time to investigate the full at-risk population. Each investigation requires reviewing multiple sources of customer evidence.

**Cost of wrong decision:**
- Missed retention opportunity for a customer who could have been retained
- Unnecessary incentive cost for a customer who would have purchased anyway
- Poor customer experience if a retention offer is used when a service issue should be addressed

**Desired improvement:** Investigate a much larger share of the weekly at-risk population while preserving the quality of the intervention decision.

---

## Persona 2 — Retention Manager

**Role:** Retention Manager

**Primary goal:** Ensure that the retention operation is using team capacity and interventions effectively.

**Information needed:**
- Weekly at-risk population size
- Investigation coverage
- Average investigation time
- Intervention distribution
- Retention-offer usage
- Support-escalation volume
- Human override or disagreement rate
- Outcome and effectiveness measures

**Decision:** Decide whether to adjust retention strategy, intervention policies, team capacity, or operating processes.

**Pain:** Limited visibility into whether the overall retention process is operating efficiently and whether interventions are producing enough value relative to their cost.

**Cost of wrong decision:** NovaCart could continue or expand an expensive retention program without evidence that the process is efficient or effective.

**Desired improvement:** Gain measurable visibility into investigation capacity, intervention patterns, decision quality, and retention-program performance.

---

## Persona 3 — Customer Support Specialist

**Role:** Customer Support Specialist

**Primary goal:** Resolve service issues for customers escalated from the retention investigation with enough context to act efficiently.

**Trigger:** A customer is escalated from the retention workflow because available evidence suggests that a service issue may require support action.

**Information needed:**
- Customer identity and account context
- Reason for escalation
- Purchase and order history
- Recent support cases
- Shipping, refund, or fulfillment issues
- Evidence supporting the escalation
- Retention Specialist notes or context

**Decision:** Determine the appropriate service resolution, such as:
- Investigate or resolve an existing case
- Issue a refund or replacement when policy permits
- Escalate to another support function
- Close the escalation if no support action is required

**Pain:** Escalations without sufficient context force Support to reconstruct the customer's history and repeat work already performed during retention investigation.

**Cost of wrong decision:** The underlying customer issue may remain unresolved, increasing the likelihood of continued dissatisfaction or churn.

**Desired improvement:** Receive context-rich escalations that reduce duplicate investigation and allow Support to act faster.

---

# Core Workflows

## Workflow 1 — Investigate an At-Risk Customer

**Owner:** Retention Specialist

**Trigger:** A customer appears in the weekly at-risk population.

**Inputs:**
- Customer identifier
- Purchase history
- Order history
- Behavioral engagement
- Cart activity
- Email engagement
- Support history

**Current steps:**
1. Open the customer's available records.
2. Review recent and historical purchases.
3. Review behavioral and engagement trends.
4. Review email engagement.
5. Review support interactions.
6. Identify signals that may explain declining activity.
7. Form an investigation summary.

**Decision:** Determine whether enough evidence exists to proceed to an intervention decision.

**Current friction:**
- Each investigation takes approximately 20–30 minutes.
- Only about 15% of the approximately 2,000 weekly at-risk customers are investigated.
- Evidence must be reviewed manually.

**Desired outcome:** Produce an evidence-backed customer investigation in substantially less specialist time so that a much larger share of the at-risk population can be evaluated.

---

## Workflow 2 — Determine the Appropriate Intervention

**Owner:** Retention Specialist

**Trigger:** A customer investigation has produced sufficient evidence about the customer's recent behavior and likely reasons for decline.

**Inputs:**
- Investigation summary
- Customer behavioral evidence
- Purchase and engagement trends
- Support history
- Relevant retention or offer eligibility information

**Current steps:**
1. Interpret the investigation findings.
2. Decide whether the customer requires intervention.
3. Compare the available action choices.
4. Choose the most appropriate intervention.

**Decision:** Choose among:
- No action
- Retention offer
- Escalate to Support

**Current friction:**
- Intervention decisions depend on manually assembled evidence.
- Similar customer situations may be evaluated inconsistently.
- Specialists have limited time to compare all relevant signals.

**Desired outcome:** Make intervention decisions using a consistent, evidence-backed process while preserving specialist judgment.

---

## Workflow 3 — Review and Approve a Proposed Intervention

**Owner:** Retention Specialist

**Trigger:** An investigation has produced a proposed intervention and the supporting evidence is available for review.

**Inputs:**
- Proposed intervention
- Investigation summary
- Supporting customer evidence
- Relevant eligibility or policy context

**Current steps:**
1. Review the evidence supporting the intervention.
2. Apply business context that may not be represented in the available data.
3. Agree with, modify, or reject the proposed intervention.
4. Record the final decision.

**Decision:** Approve, modify, or reject the proposed action.

**Current friction:**
- In the current manual process, investigation and decision-making are tightly coupled and difficult to evaluate separately.
- Decision rationale may not be consistently captured for later review.

**Desired outcome:** Keep consequential decisions under meaningful human review while capturing the evidence and rationale behind the final action.

---

## Workflow 4 — Handle a Retention-Driven Support Escalation

**Owner:** Customer Support Specialist

**Trigger:** The Retention Specialist determines that a customer should be escalated because a service issue may be contributing to declining engagement.

**Inputs:**
- Customer identifier
- Reason for escalation
- Investigation findings
- Relevant order and purchase context
- Recent support history
- Supporting evidence
- Specialist notes

**Current steps:**
1. Receive the escalation.
2. Reconstruct the customer's recent history.
3. Review existing support cases and order issues.
4. Determine the unresolved service problem.
5. Choose and execute the appropriate support resolution.
6. Record the outcome.

**Decision:** Determine the appropriate support action or whether no further support action is required.

**Current friction:**
- A weak handoff can cause Support to repeat investigation work.
- Missing context increases handling time.
- The reason the customer was escalated may not be obvious.

**Desired outcome:** Provide Support with a context-rich handoff so that the underlying customer issue can be addressed without repeating the full retention investigation.

---

## Workflow 5 — Monitor Retention Investigation Performance

**Owner:** Retention Manager

**Trigger:** A recurring retention-operations review, such as a weekly performance review.

**Inputs:**
- Weekly at-risk population
- Number and percentage investigated
- Investigation time
- Intervention distribution
- Offer volume
- Support-escalation volume
- Specialist agreement or override data
- Available outcome metrics

**Current steps:**
1. Review the size of the at-risk population.
2. Review how many customers were investigated.
3. Review intervention volumes and patterns.
4. Assess operational bottlenecks.
5. Identify whether retention policies or team processes should change.

**Decision:** Determine whether to adjust retention strategy, intervention policies, operating process, or team capacity.

**Current friction:**
- Limited visibility into the end-to-end investigation process.
- Difficult to determine whether increased intervention volume corresponds to better decisions.
- Operational and business outcomes may be reviewed separately.

**Desired outcome:** Give the Retention Manager a measurable view of investigation coverage, efficiency, intervention patterns, and decision quality.

---

# Discovery Assumptions to Validate

- The existing at-risk model produces a sufficiently useful weekly candidate population for V1.
- Investigation capacity is the primary operational bottleneck.
- Retention Specialists can define a defensible expected intervention for evaluation scenarios.
- Purchase, behavioral, email, and support evidence are available with enough historical depth to support investigation.
- Retention offers have explicit eligibility or business rules that can be represented in the project.
- Support escalations can be evaluated using a synthetic but realistic set of service scenarios.

# Open Questions

- How does NovaCart define a successful retention intervention?
- What offer eligibility rules exist?
- What information is available to the existing at-risk model versus the Retention Specialist?
- How should ambiguous cases be handled?
- What evidence should be mandatory before recommending an intervention?
- How should specialist disagreement with a recommendation be recorded?
- What is the current support-escalation handoff process?
- Which business outcomes can be measured without making unsupported causal claims?
