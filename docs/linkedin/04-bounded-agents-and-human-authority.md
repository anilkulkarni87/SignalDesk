# Post 04 - Bounded Agents and Human Authority

An agent is not trustworthy because it can call tools.

It becomes reviewable when the application owns the boundaries around those
calls.

For SignalDesk, that meant:

```text
typed tool schemas
customer-scoped arguments
deterministic execution
bounded model rounds
bounded tool calls
resolvable evidence references
explicit stopping behavior
human action authority
```

The frozen 50-task agent evaluation completed every task with correct tool
selection and arguments. It still had unnecessary tool use in one cohort, and
its 9.2174-second p95 latency missed the target below eight seconds.

Passing the task rubric did not erase the efficiency or performance result.

The action workflow introduced another separation:

> Recommendation is not authorization.

The model could participate in an investigation and propose a bounded action.
It could not approve its own payload. Approval or rejection was tied to an exact
action ID, recorded durably, and tested for duplicate prevention.

This is a synthetic coupon workflow, not evidence that autonomous customer
treatment is safe or effective. The point is the permission pattern.

The tools and agents phase covers the loop, LangGraph state, human approval, and
a runtime comparison:

https://anilkulkarni87.github.io/SignalDesk/journey/#tools-agents

#AIAgents #HumanInTheLoop #LangGraph #AIEngineering

