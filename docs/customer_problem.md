# NovaCart Customer Investigation Problem

## 1. Business Context

NovaCart has a Customer Retention team that receives approximately 2,000 at-risk customers each week.

The Retention team investigates customer behavior to determine the appropriate intervention:

- No action
- Retention offer
- Escalate to Support

The current investigation process is manual. Each investigation takes approximately 20–30 minutes, and the team is currently able to investigate only about 15% of the weekly at-risk population.

## 2. Current Workflow

At-risk customer list  
→ Review customer purchase history  
→ Review behavioral engagement  
→ Inspect email engagement  
→ Inspect support history  
→ Interpret available evidence  
→ Choose an intervention:
- No action
- Retention offer
- Support escalation

### Current Baseline

- At-risk customers: ~2,000 per week
- Investigation time: ~20–30 minutes per customer
- Investigation coverage: ~15%
- Customers investigated: ~300 per week

## 3. Problem Statement

NovaCart does not primarily have an at-risk customer identification problem because an existing model already produces the weekly at-risk population.

NovaCart has an investigation capacity and decision-support problem because retention specialists cannot investigate and make informed intervention decisions for all approximately 2,000 at-risk customers each week.

As a result, NovaCart currently lacks the capacity to evaluate approximately 85% of its weekly at-risk population, meaning potentially important intervention opportunities may go unidentified.

### Capacity Estimate

At the midpoint investigation time of 25 minutes:

- Current investigation effort:
  - 300 customers × 25 minutes
  - 7,500 minutes
  - ~125 specialist-hours per week

- Full manual coverage:
  - 2,000 customers × 25 minutes
  - 50,000 minutes
  - ~833 specialist-hours per week

Across the full 20–30 minute investigation range, manually investigating all 2,000 customers would require approximately 667–1,000 specialist-hours per week.

### Known vs Derived

#### Known
- NovaCart receives approximately 2,000 at-risk customers each week.
- Retention specialists investigate approximately 15% of that population.
- Each investigation takes approximately 20–30 minutes.
- Specialists choose among no action, retention offer, or support escalation.

#### Derived
- Approximately 300 customers are investigated each week.
- Approximately 1,700 customers are not investigated each week.
- At an average of 25 minutes per investigation, current investigation effort is approximately 125 specialist-hours per week.
- Full manual coverage would require approximately 833 specialist-hours per week at the same average investigation time.

#### Assumptions
- The existing at-risk model provides sufficiently useful candidates for V1.
- Retention specialists can consistently determine an appropriate intervention when they have sufficient evidence.
- The primary bottleneck is investigation capacity rather than another downstream constraint such as campaign capacity.

## 4. Primary User

**Role:** Customer Retention Specialist

**Goal:** Investigate at-risk customers in a timely manner and determine the appropriate intervention: no action, retention offer, or escalation to Support.

**Inputs:** A weekly list of at-risk customers and the customer evidence required to investigate their behavior, including purchase history, behavioral engagement, email engagement, and support history.

**Decision:** Choose among no action, retention offer, or escalation to Support.

**Pain:** The team does not have enough investigation capacity to evaluate the full weekly at-risk population. Each investigation also requires reviewing multiple sources of customer evidence.

## 5. V1 Product Boundary

### V1 will
- Collect relevant customer evidence.
- Summarize customer behavior.
- Identify important behavioral and service signals.
- Recommend one of the allowed interventions.
- Show the evidence supporting the recommendation.
- Keep the final intervention decision under human review.

### V1 will not
- Automatically send retention offers.
- Automatically create support escalations.
- Replace the existing at-risk model.
- Optimize discount values.
- Claim causal retention lift.

### Why SignalDesk will not replace the existing at-risk model in V1

The existing model already addresses the customer-identification step by producing the weekly at-risk population.

V1 is intentionally scoped to the unresolved bottleneck: investigation capacity and intervention decision support. Replacing the existing model would expand the project into a separate prediction problem without evidence that customer identification is currently the limiting factor.

## 6. Desired Outcome

### Investigation Coverage

Increase the proportion of the weekly at-risk population that receives a meaningful investigation.

### Investigation Efficiency

Reduce the amount of specialist time required to investigate an individual customer.

### Decision Quality

Maintain or improve the quality of intervention decisions while increasing investigation volume.
