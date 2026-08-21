# Ten-Minute FDE Demo

## Learning scope

This demo presents a synthetic learning journey and a local prototype. It must not be described as a production deployment, a customer result, or an autonomous decision system.

## Before the meeting

- Start the API and confirm `/api/v1/health` and `/api/v1/health/ready`.
- Start the frontend and sign in at `http://127.0.0.1:3000`.
- Confirm one live synthetic investigation completes and appears in Observability.
- Keep the API documentation open at `http://127.0.0.1:8001/docs` as a contract reference.
- Prepare a known synthetic customer such as `C0046145`.
- Keep this script and the [evaluation scorecard](evaluation.md) open.

## Script

### 0:00-0:45 - Set the boundary

Say:

> SignalDesk is a synthetic learning system. I will show how we moved from a customer hypothesis to a measured, controlled workflow. The goal is to demonstrate engineering and discovery discipline, not claim production readiness or business impact.

### 0:45-1:45 - Frame the customer problem

- Use the fictional baseline: fragmented customer evidence and policy lookup make investigations slow and inconsistent.
- Name the users: analyst, policy owner, approver, and operator.
- State the unvalidated hypothesis: grounded assistance could reduce investigation time without weakening controls.

Open [Discovery](discovery.md).

### 1:45-2:45 - Explain the architecture

- Show the browser, API, bounded tools, generated warehouse/knowledge, model, retrieval, workflow, and audit boundaries.
- Point out that the model does not receive database credentials and cannot approve its own action.
- Clarify that lexical retrieval and LangGraph are the accepted serving path; vector retrieval and Agents SDK were experiments.

Open [Architecture](architecture.md).

### 2:45-5:15 - Run one investigation

1. Open Workspace.
2. Search for synthetic customer `C0046145`.
3. Ask a question about the customer's warning signals and the policy constraints on the next step.
4. Show the structured conclusion, customer evidence, retrieved policy citations, and tool calls.
5. Explain that evidence provenance matters more than fluent prose.

Do not present one successful answer as an accuracy measurement; the offline suite carries that claim.

### 5:15-6:30 - Show the action boundary

- Draft the synthetic coupon action.
- Read the exact payload before deciding.
- Demonstrate either approval or rejection.
- Show the audit transitions and idempotent action ID.

Say:

> The system demonstrates approval gating. It does not prove that issuing this coupon is a good business decision.

### 6:30-7:30 - Inspect observability

- Open Observability.
- Select the recent run.
- Show latency, tokens, estimated cost, tool calls, retrieval records, and human evaluation.
- Explain how a reviewer moves from an aggregate metric to one traceable run.

### 7:30-8:45 - Present evidence and failures

- Retrieval experiment: vector Recall@5 was 98%; lexical was 68%.
- Agent suite: 50 synthetic cases completed, but p95 latency was 9.2174 seconds and missed the target.
- Failure injection: 8/8 named scenarios degraded as designed.
- Commit 17 verification: 148 tests passed after correcting CI dependency and timezone issues; the Commit 18 documentation checks bring the current total to 152.

Open [Evaluation](evaluation.md) and [Known Limitations](known_limitations.md).

### 8:45-10:00 - Make the next decision explicit

- Do not propose general rollout.
- Propose real discovery, an independent offline set, and then a read-only shadow pilot.
- Name stop conditions: cross-customer access, unsupported policy advice, unauthorized action, or missing audit evidence.
- End with the decision requested: approve, revise, or stop the next validation stage.

Open [Validation Roadmap](roadmap.md).

## Expected questions

**Did SignalDesk reduce investigation time?**  
No. The repository has a fictional 20-30 minute baseline and a target below 3 minutes, but no controlled user measurement.

**Why not use the best vector result in the app?**  
The vector benchmark showed a quality advantage, but adopting it changes dependencies, cost, latency, and operations. The serving path stays frozen until that tradeoff is accepted explicitly.

**Is the model autonomous?**  
No. It can use bounded read tools and participate in an approval-gated synthetic workflow. It cannot authorize its own action.

**Is this production ready?**  
No. Security, identity, data governance, independent evaluation, reliability, and real workflow validation remain pilot gates.

**What did the project prove?**  
It proved that this repository can generate a synthetic data substrate, evaluate retrieval and model behavior, enforce tool and approval contracts, expose a local workflow, and test named failures reproducibly.

## Demo fallback

If a live model call fails, show the typed failure and request ID in Observability, then use the frozen evaluation artifacts to continue. Do not switch to an unrecorded answer or hide the failure; graceful failure is part of the story.
