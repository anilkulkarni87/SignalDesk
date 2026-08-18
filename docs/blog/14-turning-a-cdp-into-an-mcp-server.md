# Turning a CDP Into an MCP Server

An AI system becomes useful when it can reach real customer context. That does
not mean every agent should receive a custom database integration.

SignalDesk already had deterministic tools for customer profiles, events,
knowledge, metrics, purchases, campaign constraints, and recommendation drafts.
Commit 14 asks a different question:

> How can selected CDP capabilities become reusable across MCP-compatible
> clients without weakening their existing contracts?

The answer is a thin authenticated MCP boundary over the tools we already
trust.

## Start with the integration problem

An FDE repeatedly encounters customer systems such as:

```text
warehouse
CRM
support platform
document repository
internal API
campaign system
```

Without a protocol boundary, every new model runtime needs custom code for tool
definitions, schemas, invocation, errors, and connection setup. The business
logic may be identical, but the integration is rebuilt each time.

MCP standardizes the client/server conversation:

```text
initialize
discover tools
inspect schemas
call tool
receive structured result
```

That standardization is valuable, but it is easy to overstate. MCP does not
decide which customer data is safe to expose. It does not make a query bounded.
It does not authenticate a user merely because a server speaks the protocol.
Those remain application responsibilities.

## Reuse the deterministic core

Commit 09 already created `CDPTools` and a `ToolRegistry`. They enforce:

```text
strict Pydantic inputs
typed outputs
read-only DuckDB access
bounded event windows
PII-safe profiles
current approved knowledge only
structured domain errors
```

Commit 14 does not rewrite that logic. The MCP layer maps four public names to
the existing registry:

| Public MCP name | Existing capability |
|---|---|
| `customer_profile` | `get_customer_profile` |
| `customer_events` | `get_customer_events` |
| `knowledge_search` | `search_knowledge_base` |
| `campaign_eligibility` | `get_campaign_eligibility` |

The architecture is deliberately boring:

```text
MCP request
-> authenticate
-> validate published schema
-> map public name
-> execute existing registry tool
-> return typed envelope
```

That is the point. A protocol adapter should not become a second home for
business rules.

## Capability selection is an authorization decision

The internal registry contains seven tools. The MCP server exposes four.

It omits purchase details, calculated metrics, and recommendation creation from
this learning boundary. More importantly, it exposes no Commit 12 action tool.

An integration boundary should follow least privilege:

```text
available internally != safe to expose externally
```

All four public tools are read-only and idempotent. Their MCP annotations say:

```text
readOnlyHint      true
destructiveHint   false
idempotentHint    true
openWorldHint     false
```

Annotations help clients plan. They are not a security control. The real
controls are the allow-list, absence of mutation handlers, read-only database
connection, strict schemas, and integration tests.

## JSON Schema is part of the boundary

Tool descriptions are not enough. A client needs machine-readable limits.

The published schemas retain the existing Pydantic constraints:

```text
customer IDs must match ^C\d{7}$
event windows are 1 to 90 days
event results are capped at 100
knowledge top_k is 1 to 10
families and channels are allow-listed
extra fields are forbidden
```

The extra-field rule matters. A client cannot ask for `include_email=true` and
hope an implementation accepts it accidentally. Discovery advertises
`additionalProperties: false`, and invocation rejects the call before the
business function runs.

This is one place where protocol-level tests are more useful than reading the
decorated Python function. The test asks the server what schema an external
client actually sees and then tries to violate it.

## Protocol errors and domain errors differ

Consider two failures:

```text
customer_id = "not-a-customer"
customer_id = "C9999999"
```

The first value violates the published schema. It is an invalid MCP tool call
and returns `isError=true` at the protocol level.

The second value is structurally valid, but the customer does not exist. The
call reaches SignalDesk and returns a typed domain envelope:

```text
success = false
error.code = NOT_FOUND
```

Keeping those classes separate makes operations clearer. One is a client
contract defect; the other is an expected business lookup outcome.

## Authentication belongs at the transport boundary

The server uses stateless Streamable HTTP and the MCP Python SDK's bearer-token
verification. Every MCP request requires a token with `signaldesk:read`.

The server also publishes protected-resource metadata so a client can discover:

```text
resource URL
authorization server
supported scope
bearer-token method
```

For this local exercise, the token is pre-issued through an environment
variable. It is never a command-line argument, and the verifier compares a
SHA-256 digest in constant time.

That is enough to learn the resource-server boundary. It is not production
OAuth. A deployed system would need a real authorization server, TLS,
short-lived audience-bound tokens, identity, rotation, revocation, tenant-aware
policy, and audit.

## Test the protocol, not only the functions

Commit 09 already tests the Python handlers directly. Commit 14 adds 27 tests
through the MCP Streamable HTTP application.

They cover:

```text
initialization
missing and invalid tokens
protected-resource metadata
tool discovery
input and output schemas
read-only annotations
four successful capabilities
schema rejection
domain NOT_FOUND
PII exclusion
knowledge authority and family filters
bounded event retrieval
campaign review semantics
unknown tools
deterministic repeated reads
absence of mutation names
```

All 27 passed. The full SignalDesk suite reached 109 passing tests. A separate
client process also authenticated, discovered all four tools, and called
`customer_profile` over localhost HTTP.

No model API call was needed. MCP correctness is a deterministic integration
concern; introducing model variance would make this experiment worse.

## What MCP changed and what it did not

MCP changed:

```text
discovery format
invocation protocol
transport boundary
authentication entry point
client interoperability
```

MCP did not change:

```text
customer definitions
DuckDB queries
PII policy
event limits
knowledge authority
campaign semantics
domain error model
```

That separation is the main learning outcome. Protocols should make working
capabilities portable, not redefine them.

## The FDE lesson

Customer delivery often fails at integration boundaries rather than model
quality. A useful FDE needs to ask:

```text
What capability is actually needed?
Who may call it?
Which fields may cross the boundary?
How is the contract discovered?
What is a protocol error versus a business error?
How do we test the deployed interface?
```

MCP gives a standard answer to discovery and invocation. Engineering still has
to supply the authority model, data contract, bounded behavior, and evidence
that the boundary works.

That is why turning a CDP into an MCP server is not mainly about adding four
decorators. It is about converting internal capabilities into a narrow,
explicit, testable integration product.
