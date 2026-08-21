# Lesson 10 - Bounded Agent Loops

> Learning scope: the agent operates over synthetic customers and narrow tools.
> Passing curated tasks does not prove safe autonomous customer treatment.

## Outcome

You will be able to explain an agent as a bounded model/tool loop with explicit
schemas, authority, stopping conditions, evidence provenance, and evaluation.

## Problem

A model can answer from the prompt, call the wrong tool, use invalid arguments,
repeat unnecessary work, or continue indefinitely. Adding tools creates new
failure modes rather than automatically creating a reliable agent.

## First principles

The loop is small:

```text
question + tool schemas
  -> model chooses a tool or final answer
  -> application validates name, subject, and arguments
  -> deterministic tool returns typed bounded output
  -> model continues or stops
```

The application owns permissions, schemas, execution, limits, and evidence
resolution. The model owns only the bounded choice among allowed operations.

## Build

Inspect:

- [Agent implementation](../../../../src/agent/investigator.py)
- [Tool registry](../../../../src/tools/registry.py)
- [Frozen cases](../../../../evals/commit10/cases.jsonl)
- [Full report](../../../../evals/commit10/reports/v4_full_report.json)

Trace one case from expected tools, through tool arguments and results, to the
final evidence references. Find where cross-customer access is rejected.

## Measure

The frozen 50-case report recorded:

```text
task completion              100%
correct tool selection       100%
correct tool arguments       100%
unnecessary-tools empty       98%
p95 latency                    9.2174 seconds
latency target                 below 8 seconds, not met
```

Quality success does not erase the efficiency regression or missed latency
target.

## Break

For each failure, name the owning boundary:

- The model requests another customer ID.
- A tool returns malformed JSON.
- The loop reaches its maximum rounds.
- Retrieval returns zero approved documents.
- The model gives a correct conclusion with an unresolved evidence reference.

Do not solve every failure by adding retries. Invalid arguments and exhausted
limits generally will not become correct when repeated unchanged.

## Explain

Answer in your own words:

1. What makes a tool different from an arbitrary Python function exposed to a model?
2. Which parts of an agent are deterministic application responsibilities?
3. Why is 100% task completion compatible with an unmet performance target?

## Ship

Keep an agent contract containing allowed tools, schemas, subject scope, round
and tool limits, evidence rules, task rubric, and explicit non-authority.

## Verify

```bash
python run_course.py check 10
```

The command validates the frozen configuration and runs deterministic agent
tests without calling the model provider.

## Continue

Lessons 11-17 will expand state, approval, MCP, product, observability, and
hardening. The pilot path jumps to the delivery capstone:

```bash
python run_course.py start 18
```

Deep reading: [Building a Bounded Agent](../../../../docs/blog/10-building-a-bounded-agent-by-measuring-the-loop.md).

