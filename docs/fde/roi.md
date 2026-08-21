# ROI Model

## Learning scope

This is a transparent hypothesis model for a fictional customer. It is not a forecast, realized benefit, pricing proposal, or financial recommendation. No real analyst time, adoption, retention, or revenue impact has been measured.

## Starting hypothesis

The discovery scenario assumes:

- 300 investigations per week today.
- A 20-30 minute manual investigation, with 25 minutes used as the midpoint.
- A possible future volume of 1,600 investigations per week.
- A target assisted investigation time below 3 minutes.

These inputs are fictional discovery assumptions. A real engagement would replace them with timestamped workflow data and finance-approved cost assumptions.

## Transparent formulas

Let:

- `V` = investigations per week.
- `M` = current minutes per investigation.
- `A` = assisted minutes per investigation.
- `H` = loaded analyst cost per hour.
- `U` = adoption rate from 0 to 1.
- `Q` = fraction of assisted output accepted without rework.
- `C` = incremental system cost per investigation.

Then:

```text
gross_hours_saved_per_week = V * (M - A) / 60
effective_hours_saved_per_week = gross_hours_saved_per_week * U * Q
labor_value_per_week = effective_hours_saved_per_week * H
system_cost_per_week = V * U * C
modeled_net_value_per_week = labor_value_per_week - system_cost_per_week
```

The formula intentionally discounts theoretical savings by adoption and no-rework rate. It does not translate saved time into cash unless the organization can redeploy or avoid that work.

## Capacity scenarios

Using `M = 25` and `A = 3` only as a hypothesis:

| Weekly volume | Manual hours | Assisted hours | Maximum theoretical hours released |
|---:|---:|---:|---:|
| 300 | 125.0 | 15.0 | 110.0 |
| 800 | 333.3 | 40.0 | 293.3 |
| 1,600 | 666.7 | 80.0 | 586.7 |

These are arithmetic scenarios, not measured savings. Review time, corrections, escalations, training, downtime, and change-management effort would reduce the result.

## Sensitivity example

For 300 weekly investigations and a 22-minute theoretical reduction:

| Adoption | Accepted without rework | Effective hours released/week |
|---:|---:|---:|
| 25% | 70% | 19.25 |
| 50% | 80% | 44.00 |
| 75% | 90% | 74.25 |
| 100% | 100% | 110.00 |

This table shows why model accuracy alone is not an ROI result. Workflow adoption and rework determine whether technical capability changes capacity.

## Cost evidence and omissions

Commit 10 measured an estimated generation cost of about `$0.0047` per synthetic task in one 50-case run. That is useful for model-cost sensitivity, but it excludes engineering, hosting, storage, observability, security, user support, review time, and failure handling.

A pilot should measure total variable cost per completed investigation and track fixed implementation cost separately. It should also record which tasks would have happened without the system, avoiding credit for work that merely shifted channels.

## Business outcome boundary

SignalDesk can help an analyst gather evidence and apply policy. It cannot establish that an intervention caused retention, conversion, or revenue improvement without an appropriately designed business experiment. Observational customer behavior must not be described as causal impact.

## Pilot measurement sheet

For every eligible investigation, capture:

- Start and completion time for current and assisted workflows.
- Whether the analyst used the assistant.
- Whether the first answer was accepted, corrected, or escalated.
- Severity and time cost of errors.
- Human review and action approval time.
- Model, retrieval, infrastructure, and support cost.
- Outcome definition and comparison method, if a business experiment is approved.

The pilot gate is evidence that the assisted workflow improves a pre-agreed operational metric without weakening quality or controls, not a persuasive demo.

