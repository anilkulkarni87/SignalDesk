# Breaking My AI Agent Before Production Does

By Commit 16, SignalDesk could explain what happened during an investigation.
It correlated the HTTP request, agent run, tool calls, retrieval, tokens, cost,
latency, answer, errors, and human evaluation.

That still left a more uncomfortable question:

> What happens when the assumptions underneath the successful demo stop being
> true?

Production systems spend much of their time outside the happy path. Networks
stall. Dependencies return malformed output. Users submit the same request
twice. A model continues calling tools instead of answering. A process remains
alive after its data dependency fails.

Commit 17 deliberately broke those assumptions.

## Start with failure contracts

A failure test is useful only when the expected behavior is decided before the
failure is injected.

For each scenario I wrote down four things:

```text
what fails
where the failure is detected
what the caller receives
what evidence the operator retains
```

For an LLM timeout, the contract became:

```text
detect at the investigation boundary
return HTTP 504
do not leak the provider message
persist a correlated failed run observation
do not retry forever
```

For malformed tool output, the contract was different. Tools already have
strict output schemas, so the registry converts malformed output into a typed
`VALIDATION_ERROR`. The agent can reason about a bounded failure envelope
instead of receiving an arbitrary Python exception.

The response should follow the semantics of the failure, not one universal
"something went wrong" path.

## Alive is not ready

A process can answer HTTP while being unable to produce a trusted result.

SignalDesk now separates:

```text
liveness   can this process answer?
readiness  can this instance serve the required dependencies?
```

The readiness probe checks the warehouse, approved knowledge corpus, runtime
stores, action ledger, and idempotency store. When approved knowledge is
unavailable, readiness returns `503` while liveness remains `200`.

That distinction matters to orchestration. Restart policy uses liveness.
Traffic routing uses readiness. Combining them can either restart healthy
processes unnecessarily or route work to an incapable instance.

## Retry only what may become true

Retries are not a general error-handling strategy.

A transient connection error may become successful on another attempt. A
schema violation, invalid customer, policy conflict, or exhausted agent round
limit will not become correct because the same operation ran again.

SignalDesk retries only declared transient provider exceptions with bounded
exponential backoff. The policy limits:

```text
time per provider request
attempts per provider call
model rounds per investigation
tool calls per investigation
```

When a limit is reached, the workflow stops and records why. A bounded failure
is safer and easier to debug than an unbounded attempt to succeed.

## Duplicate requests are a correctness problem

Users retry when a browser stalls. Proxies retry when a connection closes.
Without idempotency, one logical request can create multiple model calls,
multiple costs, and potentially multiple downstream actions.

Commit 17 adds a durable user-scoped idempotency key. The key binds to a hash of
the canonical request payload.

The state machine is small:

```text
PENDING -> COMPLETED
PENDING -> FAILED -> PENDING
stale PENDING -> PENDING takeover
COMPLETED -> replay
```

Submitting the same key and payload returns the persisted investigation without
another model call. Reusing the key for different input is a conflict.

This revealed an important boundary: idempotency is not just caching. It is a
durable claim about the identity and lifecycle of work.

## Capacity must fail before work starts

Rate limiting after an LLM call protects nothing.

SignalDesk applies a sliding-window limit before agent execution. Login attempts
are keyed by client address; investigations are keyed by signed user identity.
Rejected work receives `429` and `Retry-After` without consuming model or tool
capacity.

The implementation is intentionally in-memory because this is one local
instance. A distributed deployment would move quota state to shared storage or
an edge gateway. Calling the local limiter "distributed" would teach the wrong
lesson.

## Logs need correlation, not payloads

The API now emits JSON request events with request ID, method, path, status, and
duration. It does not log request bodies, credentials, or raw provider errors.

The request ID joins HTTP behavior to the run observation from Commit 16. A
structured format makes that join machine-queryable later, while minimizing
the chance that debugging creates a second data leak.

Structured logging is not the same as having an observability platform. There
is still no external log shipper, retention policy, trace backend, or alerting
system. The local contract is the part this milestone can honestly prove.

## Packaging is part of reliability

The first container build worked, but inspection found two issues.

First, the frontend dependency audit identified high-severity advisories in the
installed Next.js release. Upgrading to the patched non-major version reduced
the production audit to zero known vulnerabilities.

Second, the initial frontend image copied development dependencies into the
runtime image and was about 727 MB. Switching Next.js to standalone output
reduced it to about 225 MB. Both API and web images run as non-root users.

The lesson is practical: a successful build is not the end of container
verification. Dependency findings, runtime user, image contents, readiness, and
actual startup all matter.

## Break the real dependency

The roadmap listed "vector DB unavailable." SignalDesk's accepted serving path
does not use the old vector store; it uses bounded lexical retrieval over
approved knowledge.

Testing an unused vector database would create a green metric with no runtime
meaning. The failure injection therefore disables the actual approved-knowledge
dependency and verifies readiness behavior.

Hardening should follow the deployed architecture, not historical experiments.

## Measure without overclaiming

The deterministic hardening suite produced:

```text
8/8 failure scenarios passed
147 repository tests passed
92% API-boundary statement coverage
0 production npm vulnerabilities
```

The final API container also handled 100 concurrent liveness-path requests with
100% success, zero unhandled exceptions, and 48.749 ms p95.

That result does not establish model-backed investigation capacity. A health
endpoint avoids the LLM, retrieval workflow, and Customer 360 analysis. The
number proves that the container and HTTP boundary survive a small smoke load,
not that the system meets a production workload SLO.

## The FDE lesson

An FDE cannot stop at "the demo worked." The customer also needs to know:

```text
what fails safely
what retries
what does not retry
what is deduplicated
what stops receiving traffic
what an operator can inspect
what remains unproven
```

Breaking the system deliberately turns architecture assumptions into evidence.
It also creates the runbook material needed for the final FDE delivery pack.

The result is not an indestructible agent. It is a system whose known failure
modes have bounded, observable behavior.
