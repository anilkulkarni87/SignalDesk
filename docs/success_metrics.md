# SignalDesk Success Metrics

These metrics define how SignalDesk V1 will be evaluated. Initial targets are hypotheses to validate during implementation and testing rather than guarantees of real-world business impact.

## 1. Investigation Coverage

**Definition:**  
Percentage of the weekly at-risk population that receives a completed, evidence-backed investigation.

**Baseline:**  
Approximately 15%.

**Initial target:**  
At least 80%.

**How measured:**  
For each weekly at-risk population:

Investigation Coverage = Completed Investigations / Total At-Risk Customers × 100

A completed investigation must contain enough customer evidence to support an intervention decision. Merely opening or partially processing a customer record does not count as completed.

For NovaCart's current weekly volume of approximately 2,000 at-risk customers:

- Current baseline: ~300 completed investigations
- 80% target: at least 1,600 completed investigations

**Why it matters:**  
The current bottleneck is investigation capacity. Increasing coverage means a much larger share of the at-risk population can receive a meaningful review without assuming that every investigated customer should receive an intervention.

---

## 2. Investigation Efficiency

**Definition:**  
Elapsed human workflow time required for a Retention Specialist to investigate one customer and reach a point where they can make or approve an intervention decision.

**Baseline:**  
Approximately 20–30 minutes per customer.

**Initial target:**  
Less than 3 minutes per customer.

**How measured:**  
Measure elapsed time from when a specialist begins reviewing an at-risk customer to when they have enough evidence to make or approve the final intervention decision.

The measurement should include:

- Reviewing the investigation summary
- Inspecting supporting evidence
- Resolving any unclear findings
- Making or approving the intervention decision

The measurement should not be limited to backend processing or response latency.

Evaluation should report:

- Median investigation time
- p95 investigation time
- Percentage of investigations completed within 3 minutes

**Why it matters:**  
Reducing investigation time directly addresses the current capacity constraint. A fast backend is not useful if specialists still spend significant time reconstructing the customer story or validating the recommendation.

---

## 3. Decision Quality

**Definition:**  
Percentage of evaluation scenarios where the final recommended intervention matches the expected intervention defined for the scenario.

**Baseline:**  
Unknown.

**Initial target:**  
At least 85% accuracy on the evaluation dataset.

**How measured:**  
Create a labeled evaluation dataset containing synthetic customer investigation scenarios.

Each evaluation case should contain:

- Customer profile
- Purchase and order history
- Behavioral engagement
- Email engagement
- Support history
- Relevant eligibility or policy context
- Expected intervention
- Evidence supporting the expected intervention
- Ambiguity status

Allowed expected interventions are:

- `NO_ACTION`
- `RETENTION_OFFER`
- `ESCALATE_TO_SUPPORT`

A case counts as **correct** when SignalDesk's recommended intervention exactly matches the expected intervention.

A case counts as **incorrect** when:

- The recommended intervention differs from the expected intervention
- The system fails to return an allowed intervention
- The system cannot complete the investigation despite sufficient evidence being available

For clearly labeled cases:

Decision Accuracy = Correct Recommendations / Total Non-Ambiguous Evaluation Cases × 100

### Ambiguous cases

Some scenarios may reasonably support more than one intervention. These cases should not be forced into a single-label accuracy metric.

Ambiguous cases should be marked explicitly and evaluated separately.

For an ambiguous case, the evaluation record should define:

- Acceptable intervention set
- Why the case is ambiguous
- Evidence required for a defensible answer

A recommendation is considered acceptable if it falls within the predefined acceptable intervention set and its rationale is supported by the evidence.

Report ambiguous-case performance separately from primary decision accuracy.

**Why it matters:**  
Increasing investigation volume is only useful if intervention quality is preserved. This metric provides a repeatable way to test recommendation behavior as the system changes.

This metric measures agreement with the expected answer in a synthetic evaluation set. It does not prove that the recommendation would cause better real-world retention outcomes.

---

## 4. Evidence Quality

**Definition:**  
Percentage of material claims in an investigation that are supported by the underlying customer evidence.

**Baseline:**  
Unknown.

**Initial target:**  
At least 95% of material claims supported by evidence.

**How measured:**  
For each evaluation investigation, identify material factual claims that influence the diagnosis or recommendation.

Examples include:

- Purchase frequency declined by a stated amount
- Customer has unresolved support tickets
- Email engagement decreased
- Customer is eligible for a retention offer
- Recent orders experienced fulfillment problems

Each material claim should be mapped to its supporting source, such as:

- Purchase history
- Behavioral events
- Email engagement
- Support records
- Deterministically calculated customer metrics
- Eligibility or policy records

Evidence Support Rate = Supported Material Claims / Total Material Claims × 100

A claim counts as unsupported if:

- No corresponding evidence exists
- The evidence contradicts the claim
- The system states a precise value that cannot be derived from the available data

Evaluation should also record the number of unsupported claims per investigation.

**Why it matters:**  
A recommendation can appear plausible while relying on incorrect or invented facts. Evidence quality is therefore measured separately from intervention accuracy so that coincidentally correct answers with unsupported reasoning do not pass unnoticed.

---

## 5. System Responsiveness

**Definition:**  
Elapsed system time required to return a completed investigation after a valid investigation request is submitted.

**Baseline:**  
Not yet established.

**Initial target:**  
p95 response time below 8 seconds.

**How measured:**  
Record timestamps around every investigation request:

- Request received
- Investigation completed
- Response returned

System Response Time = Response Returned Timestamp - Request Received Timestamp

Report at minimum:

- p50 response time
- p95 response time
- Maximum response time
- Number of timed-out or failed requests

The p95 target means at least 95% of valid investigation requests should complete in less than 8 seconds under the defined test workload.

System responsiveness must be measured separately from Investigation Efficiency because a fast system response does not automatically produce a fast human workflow.

**Why it matters:**  
Retention Specialists need the system to respond quickly enough to remain useful within an interactive investigation workflow. Tail latency matters because consistently slow outlier requests can damage usability even when average latency appears acceptable.

---

# Metric Hierarchy

SignalDesk metrics should be interpreted at different levels:

1. **Workflow outcome**
   - Investigation coverage
   - Investigation efficiency

2. **Decision/product quality**
   - Decision quality
   - Evidence quality

3. **System quality**
   - System responsiveness

Business outcomes such as retention lift, incremental revenue, or promotion ROI should be evaluated separately using an appropriate experimental design. V1 should not claim causal business impact based only on synthetic data or recommendation accuracy.

# Initial V1 Targets Summary

| Metric | Baseline | Initial target |
|---|---:|---:|
| Investigation Coverage | ~15% | >=80% |
| Investigation Efficiency | 20–30 min/customer | <3 min/customer |
| Decision Quality | Unknown | >=85% |
| Evidence Quality | Unknown | >=95% |
| System Responsiveness | N/A | p95 <8 sec |

These targets should be revisited after the first measurable prototype and evaluation run.
