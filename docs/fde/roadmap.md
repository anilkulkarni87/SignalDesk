# Validation Roadmap

## Learning scope

This roadmap describes how a team could move from the synthetic learning system toward a real, controlled pilot. It is not a commitment to deploy SignalDesk or a reason to add more framework features.

## Guiding rule

The next stage should reduce the largest decision uncertainty. More prompts, retrievers, agents, or orchestration frameworks are not progress unless evidence shows they address a measured constraint.

## Stage 0: Freeze the learning baseline

**Objective:** preserve what was demonstrated and its limits.

- Tag the accepted revision and archive evaluation inputs, outputs, model, reasoning setting, and dependency versions.
- Retain the current-known failures and unmet latency target.
- Agree that vector retrieval and Agents SDK results are experiments, not implicit serving changes.

**Exit:** another engineer can reproduce the documented tests and identify the accepted runtime path.

## Stage 1: Real discovery and data contract

**Objective:** validate that the problem and workflow exist as described.

- Observe representative investigations and measure baseline time, rework, escalation, and outcome definitions.
- Interview analysts, policy owners, security, data owners, and operations.
- Inventory minimum required fields, source freshness, identity rules, policy authority, and forbidden data.
- Define pilot users, non-users, and explicit out-of-scope decisions.

**Exit:** signed discovery brief, approved minimum data contract, baseline measurements, and named owners.

## Stage 2: Offline representative evaluation

**Objective:** test quality on independent, production-like cases without serving users.

- Create a de-identified and independently labeled evaluation set.
- Measure inter-rater agreement, cohort failures, stochastic variance, latency, and full cost.
- Red-team cross-customer access, prompt injection, unsupported policy advice, and action payloads.
- Select retrieval and model configurations from evidence, including an explicit lexical-versus-vector decision.

**Exit:** quality thresholds pass, severe-failure count is zero, and residual risks are accepted by named owners.

## Stage 3: Read-only shadow pilot

**Objective:** measure workflow value without influencing customer treatment.

- Run suggestions beside the current analyst process.
- Hide outputs from operational decisions initially, then allow review without action execution.
- Compare time, first-answer acceptance, corrections, escalations, and user trust.
- Operate production-grade identity, authorization, secrets, telemetry, retention, and incident response.

**Exit:** pre-agreed productivity or quality metric improves, controls hold, and analysts choose to continue.

## Stage 4: Limited assisted workflow

**Objective:** let approved users rely on grounded recommendations within narrow boundaries.

- Start with read-only decisions and mandatory citation review.
- Use feature flags, cohort limits, quotas, and a kill switch.
- Review failures weekly and maintain a frozen regression suite from pilot incidents.
- Keep every externally meaningful action outside the model's direct authority.

**Exit:** sustained SLOs, acceptable error/rework rates, support readiness, and governance approval.

## Stage 5: Approval-gated action experiment

**Objective:** validate one reversible, low-risk action with human authorization.

- Define exact eligible payloads and idempotency behavior.
- Require role-based approval, expiry, audit, reconciliation, and rollback.
- Measure approval time, rejection reasons, duplicate prevention, and downstream correctness.
- Stop immediately for unauthorized execution, cross-customer impact, or audit gaps.

**Exit:** action control evidence passes over an agreed duration and volume; broader actions require a new review.

## Deferred until evidence requires them

- Additional agents or autonomous planning.
- A different orchestration framework.
- A production vector database.
- Multi-region deployment.
- Automated customer treatment.
- Business-outcome optimization.

The deliverable from each stage is a decision with evidence: proceed, revise, or stop.

