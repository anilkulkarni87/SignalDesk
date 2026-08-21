# Turning an AI Prototype Into a Product Someone Can Actually Use

An AI prototype can answer a question and still fail as software.

SignalDesk already had the hard internal pieces: a semantic Customer 360,
evaluated prompts, grounded retrieval, typed tools, a bounded agent loop, a
stateful LangGraph workflow, and durable human approval. Yet an analyst still
needed Python commands and JSON reports to use them.

Commit 15 asks a product question:

> Can an analyst complete the original customer investigation in one coherent,
> reviewable interface?

## Start from the human job

The original workflow takes roughly 20 to 30 minutes. An analyst finds a
customer, reconstructs recent behavior, checks policy, decides what the
evidence means, and records a next step.

The product surface should mirror that sequence:

```text
find customer
-> inspect current context
-> ask an investigation question
-> review evidence and policy
-> inspect how the answer was produced
-> authorize or reject an exact action
```

This is why the first screen is an analyst workspace rather than a product
landing page. The interface prioritizes scanning and repeated work: a
warning-first queue on the left, Customer 360 and conversation in the center,
and evidence, sources, tools, and timeline on the right.

## The API is a product boundary

It would have been easy to expose internal Python objects directly. That would
couple the browser to model SDK responses, LangGraph state, and tool internals.

Instead, FastAPI publishes explicit response models:

```text
CustomerSearchItem
Customer360View
InvestigationView
ToolExecutionView
SourceView
ActionPackageView
```

Those models answer a useful question: what does the analyst actually need to
see?

The investigation response contains the accepted answer, grounded evidence,
retrieved sources, compact tool summaries, graph transitions, and run metrics.
It does not expose secrets, database handles, arbitrary tool execution, or raw
provider payloads.

## Reuse the system that already earned trust

Commit 15 adds almost no new domain logic.

Customer 360 calls the existing typed tools. The investigation endpoint invokes
the accepted LangGraph workflow. Policy sources come from the tool trace. The
approval endpoint delegates to the durable Commit 12 state machine.

```text
new product shell
-> existing tested contracts
```

That direction matters. Rewriting customer metrics or approval behavior inside
an HTTP handler would create two definitions of the same business rule.

## Browser integration creates a new trust boundary

A terminal script runs as the developer. A browser accepts requests from a
user and sends them over a network boundary, even on localhost.

The learning implementation therefore introduces:

```text
signed HttpOnly session cookie
SameSite=Strict policy
CSRF token for writes
explicit CORS origins
per-user investigation ownership
environment-only secrets
```

This is not enterprise authentication. There is no SSO, tenant model, managed
secret store, or revocation service. But it establishes the right shape: the
server authenticates and authorizes; the browser does not grant itself access.

## Reviewability is a feature

An answer alone is insufficient for a consequential customer workflow.

The UI separates four supporting views:

- Evidence shows the customer fields behind the conclusion.
- Sources show retrieved policy documents and which were cited.
- Tools show what actually ran and whether it succeeded.
- Timeline shows the explicit workflow transitions.

This is not a substitute for observability. Commit 16 will record complete run
telemetry across requests. It is the analyst-facing provenance needed to assess
one result.

## Approval means approving bytes, not intent

The action dialog displays the exact structured payload, recommendation,
expected impact, and customer before enabling approve or reject.

The action is a synthetic support follow-up drafted by the analyst workspace.
That qualification is important. The accepted investigation agent did not
learn a new action-selection policy in this commit.

Approval remains durable and idempotent. An approved payload creates one
synthetic event. A rejected payload creates none. A completed decision cannot
be reversed by submitting the endpoint again.

## Measure the workflow, not the spinner

The roadmap target is less than three minutes, down from 20 to 30. Agent latency
does not prove that target.

The relevant clock starts when an analyst begins reviewing a customer and ends
when they have enough evidence to record a decision. The measurement includes
reading, source inspection, ambiguity resolution, and approval.

SignalDesk should report:

```text
median human workflow time
p95 human workflow time
percentage completed under three minutes
API response latency as a separate metric
```

The product now makes that study possible. The result remains unproven until
representative users complete timed runs.

## What this teaches an FDE

Forward-deployed work spans more than model behavior. A useful system must fit
the customer's operating path.

That requires asking:

```text
What does the user need to decide?
Which context must be visible at once?
Which internal details need stable API contracts?
Where are authentication and authorization enforced?
How does a reviewer verify evidence and execution?
Which metric reflects human value rather than system activity?
```

Commit 15 turns SignalDesk from a collection of strong technical components
into a coherent local product. It does not make the system production-ready.
It makes the next production questions concrete.
