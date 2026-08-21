# Post 05 - The Demo Worked. Then I Broke It.

By the time SignalDesk had an analyst workspace, a successful investigation was
no longer the interesting test.

The more useful questions were:

- What happens when policy retrieval is unavailable?
- What does the caller receive when the model times out?
- Can the same request create duplicate work?
- What if a tool returns malformed output?
- What stops an agent loop?
- Can the process be alive but unable to serve trusted answers?

Commit 17 turned those questions into eight explicit failure contracts.

```text
named failure scenarios       8/8 passed
API-boundary coverage         92%
unhandled failure-suite errors 0
external model calls           0
```

The system also separated liveness from readiness, persisted idempotency keys,
bounded retries and capacity, sanitized provider failures, and connected each
request to an inspectable run.

The first clean GitHub runner then found assumptions my local environment had
hidden: an undeclared timezone dependency and a DuckDB calculation affected by
the host timezone.

That failure was part of the learning result.

Production-minded engineering is not making a demo impossible to break. It is
deciding how known failures are bounded, observable, recoverable, and honest.

The product and operations phase:

https://anilkulkarni87.github.io/SignalDesk/journey/#product-operations

#LLMOps #Observability #ReliabilityEngineering #AIAgents

