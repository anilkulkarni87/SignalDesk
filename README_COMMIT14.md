# SignalDesk Commit 14 - CDP MCP Server

Commit 14 exposes four existing SignalDesk capabilities through an authenticated
Model Context Protocol server:

```text
customer_profile
customer_events
knowledge_search
campaign_eligibility
```

The goal is standardized integration, not new agent behavior.

## Question

> Can an external MCP client discover and call bounded CDP capabilities without
> weakening the contracts already enforced inside SignalDesk?

Commit 09 created deterministic Python tools. Commit 14 publishes a selected
read-only subset over MCP while retaining the same Pydantic schemas, registry,
DuckDB queries, knowledge-authority filters, PII boundary, and domain errors.

## Architecture

```text
MCP client
  -> Streamable HTTP
  -> bearer-token verification (signaldesk:read)
  -> MCP tool discovery and invocation
  -> strict flat JSON Schema
  -> thin public-name adapter
  -> Commit 09 ToolRegistry
  -> read-only DuckDB + current approved knowledge
```

MCP standardizes how a client discovers and calls capabilities. It does not
replace application authorization or business logic.

## Published tools

| MCP tool | Existing registry tool | Boundary |
|---|---|---|
| `customer_profile` | `get_customer_profile` | PII-safe profile only |
| `customer_events` | `get_customer_events` | 1-90 days, at most 100 events |
| `knowledge_search` | `search_knowledge_base` | Current approved documents only |
| `campaign_eligibility` | `get_campaign_eligibility` | Block or review; never final eligibility |

The other Commit 09 tools are deliberately not exposed. In particular, the MCP
server has no recommendation, approval, or action-execution capability.

Every published tool declares:

```text
readOnlyHint      true
destructiveHint   false
idempotentHint    true
openWorldHint     false
side effects      none
```

These annotations help clients reason about tools, but tests and application
structure enforce the actual boundary.

## Strict schemas

MCP discovery returns flat input schemas derived from the existing strict
Pydantic models. All four schemas publish `additionalProperties: false`.

Examples of enforced constraints include:

```text
customer_id     ^C\d{7}$
event days      1..90
event limit     1..100
knowledge top_k 1..10
channel         EMAIL | SMS | PUSH
knowledge family allow-list
```

Invalid protocol arguments produce an MCP tool error. Valid arguments that
reach a known domain failure, such as an unknown customer, return SignalDesk's
typed `ToolCallResult` with `success=false` and `NOT_FOUND`. This preserves the
distinction between a malformed call and a valid call with a business error.

## Authentication

The Streamable HTTP endpoint requires a bearer token with the
`signaldesk:read` scope. The server uses the MCP Python SDK's `TokenVerifier`
and publishes protected-resource metadata for authorization discovery.

For this local learning system, the token is pre-issued through
`SIGNALDESK_MCP_TOKEN`. It is hashed before comparison and never accepted as a
command-line argument, which avoids exposing it in process listings.

This is not a complete OAuth deployment. A production server would use a real
authorization server, short-lived audience-bound tokens, TLS, authenticated
identities, rotation, revocation, and centrally managed scopes.

## Transport

Commit 14 uses stateless Streamable HTTP with JSON responses. The MCP Python SDK
documents Streamable HTTP as the deployment transport; stdio remains useful
when a local host launches the server as a subprocess.

Official references:

- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Running MCP servers](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/run/index.md)

## Install

Use the SignalDesk Python 3.13 environment:

```bash
python -m pip install -r requirements-commit14.txt
```

The MCP SDK is pinned to `1.29.0`. Commit 13 already introduced it transitively
through the OpenAI Agents SDK; Commit 14 pins the direct dependency because the
application now imports and depends on MCP APIs itself.

## Run the server

Generate and export a local token:

```bash
export SIGNALDESK_MCP_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
python run_mcp_server.py
```

The endpoint is:

```text
http://127.0.0.1:8000/mcp
```

The default protected-resource metadata endpoint is:

```text
http://127.0.0.1:8000/.well-known/oauth-protected-resource/mcp
```

Keep the server running and use a second terminal with the same token:

```bash
export SIGNALDESK_MCP_TOKEN="the-same-token"
python run_mcp_client_demo.py
```

The client performs a real MCP initialization, lists the four tools, and calls
`customer_profile` for `C0000001`.

## Verification

```bash
python -m unittest tests.commit14.test_mcp_server -v
python -m unittest discover -s tests -v
python -m ruff check \
  src/mcp_server tests/commit14 run_mcp_server.py run_mcp_client_demo.py
python -m pip check
```

Measured result:

```text
roadmap target                    result
--------------                    ------
MCP tools                         4
strict JSON schemas               4/4
bearer authentication             enforced
integration tests                 27/27 passed
full repository tests             109/109 passed
external model API calls          0
write-capable MCP tools            0
```

The separate server/client smoke test also discovered all four tools and
returned a PII-safe profile over authenticated localhost HTTP.

## What this milestone teaches

1. MCP is an integration protocol, not an agent or business-logic framework.
2. Tool discovery and invocation can be standardized without duplicating
   domain logic.
3. JSON Schema is part of the security and reliability boundary.
4. Authentication belongs at the network resource boundary; authorization
   still needs application scopes and tool allow-lists.
5. Tool annotations communicate intent but do not enforce side-effect safety.
6. Protocol errors and domain errors are different failure classes.
7. Expose the minimum capability set a client needs.

## Limitations

This remains a local learning server. It has one pre-issued static token, no
token-issuing authorization server, no TLS, no rate limit, no per-tenant data
policy, no distributed tracing, and no deployment configuration. DuckDB is
opened read-only, but the service is not designed for concurrent production
traffic.

No LLM is called in this milestone. The accepted SignalDesk model configuration
remains `gpt-5.6-luna` with reasoning `none` for model-driven workflows, but MCP
transport correctness is deterministic and should not depend on a model.
