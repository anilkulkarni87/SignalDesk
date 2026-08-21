# Lesson 18 - FDE Evidence and Delivery Capstone

> Learning scope: the capstone presents a synthetic portfolio system. It is not
> a production handoff, customer case study, or claim of achieved ROI.

## Outcome

You will be able to present a customer hypothesis, architecture, measured
evidence, controls, failures, economics, limitations, and next reversible
decision in ten minutes.

## Problem

A technically sophisticated repository can still fail as a delivery. A mixed
audience needs to know what problem was investigated, what the system actually
does, what evidence supports it, what remains uncertain, and what decision is
being requested.

## First principles

FDE delivery connects seven layers:

```text
customer workflow
  -> requirements
  -> architecture and authority
  -> evaluation evidence
  -> operational behavior
  -> economics and limitations
  -> next validation decision
```

Every claim should be labeled measured, demonstrated, inferred, or hypothesis.

## Build

Read the [FDE delivery pack](../../../../docs/fde/README.md), then rehearse the
[ten-minute demo](../../../../docs/fde/demo.md).

Use the running Workspace only for one representative investigation. Spend the
rest of the presentation on evidence, boundaries, failures, and the next
decision.

## Measure

Your scorecard must preserve both successes and misses:

```text
vector Recall@5 experiment        98%
accepted serving retrieval        lexical_current_approved
Commit 10 task completion         50/50
Commit 10 p95 latency             9.2174 seconds
latency target                    below 8 seconds, not met
failure scenarios                 8/8 passed
real analyst time                 not measured
business impact                   not measured
```

Ask a reviewer to identify any sentence that converts synthetic evidence into
a customer or production claim.

## Break

Prepare for these challenges:

- "Your suite says 100%; is the system 100% accurate?"
- "Why is the best vector retriever not serving the application?"
- "Did the system reduce investigation time?"
- "Can the agent execute customer treatment autonomously?"
- "Why should anyone trust a generated policy corpus?"

A defensible answer states the evidence boundary before defending the design.

## Explain

Answer in your own words:

1. What did SignalDesk prove, and what did it only demonstrate?
2. Which failed or unknown metric most affects the next decision?
3. Why is real discovery the next step rather than another AI feature?

## Ship

Keep the problem frame, architecture decision record, evaluation scorecard,
security boundaries, runbook, ROI sensitivity model, known limitations, and
ten-minute demo as one portfolio package.

## Verify

```bash
python run_course.py check 18
```

The check validates the delivery-pack contract and local links. It cannot grade
the clarity or honesty of your spoken presentation.

## Continue

Run the capstone twice: once for an engineering audience and once for an
executive/customer audience. Record which questions differ and revise the
presentation without changing the underlying evidence.

Deep reading: [Delivering Evidence, Not a Demo](../../../../docs/blog/18-from-ai-engineer-to-fde-delivering-evidence-not-a-demo.md).
