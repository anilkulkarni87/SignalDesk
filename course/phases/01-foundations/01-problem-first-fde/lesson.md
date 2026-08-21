# Lesson 01 - Problem-First FDE Discovery

> Learning scope: NovaCart and every workflow in this lesson are fictional and
> synthetic. The documents demonstrate a discovery method, not completed
> customer research.

## Outcome

You will be able to turn a vague request for an AI agent into a workflow,
measurable hypothesis, safety boundary, and explicit list of unknowns.

## Problem

"Build an AI retention agent" is not a testable problem. It names a technology
and a desired outcome but omits the user, present workflow, bottleneck,
authority, evidence, and failure cost.

Read these in order:

1. [Customer problem](../../../../docs/customer_problem.md)
2. [Discovery notes](../../../../docs/discovery_notes.md)
3. [Success metrics](../../../../docs/success_metrics.md)
4. [Requirements](../../../../docs/requirements.md)

Before reading the metrics, predict which measure should sit above model
accuracy in the hierarchy.

## First principles

A system is useful only when it changes a constrained workflow without making a
more important outcome worse.

```text
user + current workflow + bottleneck
  -> intervention hypothesis
  -> observable metric
  -> countermetric and authority boundary
```

SignalDesk separates system responsiveness from human investigation time. An
eight-second response does not prove that an analyst can make a good decision
in three minutes.

## Build

Create a one-page problem frame in your notes containing:

```text
user
current trigger
current evidence sources
current decision
bottleneck
hypothesis
primary metric
countermetric
human authority
largest unknown
```

Do not mention a model, agent framework, or vector database in the problem
statement.

## Measure

Inspect the metric hierarchy in [Success metrics](../../../../docs/success_metrics.md).
Classify each metric as one of:

```text
workflow outcome
decision quality
evidence quality
system behavior
```

Then identify which baselines are fictional, unknown, or directly measured.

## Break

Try to invalidate the proposed solution:

- What if analysts are constrained by approval queues rather than investigation?
- What if the upstream at-risk population is wrong?
- What if faster investigations produce more low-quality interventions?
- What if policy lookup, not customer evidence, consumes most of the time?

These questions do not block building. They define what later evidence must
establish.

## Explain

Answer in your own words:

1. Why is "build an agent" not a customer requirement?
2. Why must investigation time and API latency remain separate metrics?
3. Which decision must remain with a human in this workflow, and why?

## Ship

Keep your one-page problem frame. It becomes the opening section of the FDE
capstone and the standard against which every later technical choice is judged.

## Verify

This check confirms that the frozen discovery, requirements, and metric
artifacts exist. It does not grade your understanding.

```bash
python run_course.py check 01
```

Complete the lesson with a reflection that states the workflow hypothesis and
one unresolved assumption.

## Continue

Continue to Lesson 02:

```bash
python run_course.py start 02
```

Deep reading: [Thinking Like an FDE](../../../../docs/blog/01-thinking-like-an-fde.md).
