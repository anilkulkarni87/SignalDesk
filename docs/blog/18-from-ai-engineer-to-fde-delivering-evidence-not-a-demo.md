# From AI Engineer to FDE: Delivering Evidence, Not a Demo

Seventeen milestones built SignalDesk from a deterministic customer data model
into a local, observable, failure-aware AI workflow.

Commit 18 added no new model behavior.

That restraint is the point.

An AI engineer can spend months improving a system and still fail to answer the
questions that determine whether anyone should use it:

```text
Whose problem is this?
What changed in their workflow?
Which claims are measured?
Which claims are still hypotheses?
What can fail?
Who has authority?
What is the next reversible decision?
```

The final learning milestone turns the repository into an FDE delivery pack.

## A working system is not yet a customer outcome

SignalDesk has substantial synthetic evidence. It generated 100,000 customers
and more than seven million rows. It benchmarked retrieval, grounded model
answers, tested deterministic tools, compared agent runtimes, implemented
durable human approval, exposed MCP tools, built a local UI, added
observability, and injected failures.

Those facts are useful. None proves that a real analyst saved time or that a
customer outcome improved.

The fictional discovery scenario says an investigation takes 20-30 minutes and
sets a target below three minutes. No user study measured either number in this
project. Converting that scenario into "SignalDesk reduced investigation time"
would turn a hypothesis into a false result.

The delivery pack therefore uses four labels:

```text
measured       produced by a versioned report or test
demonstrated   observed in the local workflow
inferred       a reasoned conclusion from evidence
hypothesis     requires representative users or data
```

This vocabulary prevents confidence from expanding as the story moves away
from the code.

## Preserve the inconvenient measurements

A delivery narrative is most trustworthy when it retains evidence that does
not fit a success story.

Vector retrieval reached 98% Recall@5 in the curated Commit 06 benchmark,
compared with 68% for lexical retrieval. The accepted product path still uses
the deterministic current-approved lexical retriever. The vector result is an
experiment, not a hidden claim about serving quality.

The Commit 10 agent completed all 50 synthetic tasks, but p95 latency was
9.2174 seconds. The roadmap target was below eight seconds. Quality passed;
latency did not.

Commit 05 created a useful prompt harness, but its original V2 was a
behaviorally identical placeholder. Review also found ambiguous evidence in
the first case set. That comparison shows repeatability, not prompt
improvement.

An FDE does not erase these distinctions. They determine the next experiment.

## Architecture is a decision record

By the end of a long build, a repository contains many ideas that are no longer
on the serving path.

SignalDesk experimented with vector retrieval and an alternate agent SDK. Its
accepted local product uses lexical retrieval and LangGraph. The architecture
document states both facts.

That matters operationally. A runbook should diagnose the dependencies that
actually serve traffic. A security review should evaluate real tool authority.
A load test should exercise the path that users invoke. Historical experiments
remain evidence, but they do not become architecture by proximity.

The accepted boundary is deliberately narrow:

```text
browser -> authenticated API -> bounded tools and retrieval
        -> model-directed LangGraph workflow -> grounded answer
        -> human-reviewed exact action payload -> synthetic execution
```

The model can propose and explain. It cannot approve its own action.

## ROI begins as algebra

The fictional baseline allows a useful capacity calculation.

At 300 investigations per week, moving from 25 minutes to three minutes would
release at most 110 hours per week. At 1,600 investigations, the theoretical
maximum is about 587 hours.

Those are arithmetic scenarios, not benefits.

Realized value depends on adoption, answer acceptance, rework, escalation,
training, downtime, and whether released capacity can be used. The ROI model
therefore discounts theoretical savings:

```text
effective hours = volume * time reduction * adoption * no-rework rate
```

It keeps model cost visible too. Commit 10 measured about $0.0047 of generation
cost per synthetic task, but that excludes engineering, hosting, security,
support, and human review.

An honest business case is a measurement plan before it is a number.

## A demo should expose the boundaries

The ten-minute demo does not spend all ten minutes on a successful answer.

It starts with the fictional scope, shows one grounded investigation, inspects
the exact approval payload, opens the observability trace, presents the failed
latency target, and ends with known limitations and a next-stage decision.

If a live model call fails, the script keeps the failure visible and uses the
frozen reports to continue. Hiding the failure would contradict the hardening
work from Commit 17.

The demo's purpose is not applause. It is to make a decision possible.

## The next feature is discovery

After a system becomes technically rich, adding another framework feels like
momentum. It may only avoid the harder uncertainty.

SignalDesk's largest unknowns are no longer whether a tool can return typed
JSON or whether an approval can resume. They are whether the workflow is real,
whether independent experts agree with the labels, whether analysts accept the
answers, and whether the system improves work without weakening controls.

The validation roadmap therefore starts with observation and a minimum data
contract. It proceeds to an independently labeled offline set, a read-only
shadow pilot, a limited assisted workflow, and only then one reversible,
approval-gated action.

Every stage has an exit decision:

```text
proceed
revise
stop
```

That is the shift from building an AI artifact to delivering an outcome: the
work is organized around reducing decision uncertainty, not accumulating
features.

## What Commit 18 taught me

The final artifact is not a claim that SignalDesk is production ready. It is a
traceable account of what the project measured, what it demonstrated, what it
failed to meet, and what a real pilot would need to establish.

The FDE lesson is simple:

> A persuasive demo shows capability. A defensible delivery connects customer
> discovery, architecture, controls, evidence, operations, economics, and the
> next reversible decision.

The first can open a conversation. The second lets a customer decide what to do
next.
