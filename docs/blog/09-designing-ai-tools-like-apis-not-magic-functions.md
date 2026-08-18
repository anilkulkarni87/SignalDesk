# Designing AI Tools Like APIs, Not Magic Functions

The word "tool" can make an AI system sound more autonomous than it really is.
A model emits a function name and arguments. Application code still has to
decide whether those arguments are valid, what data can be read, what result is
returned, and whether anything is allowed to change.

That leads to a useful first principle:

> An AI tool is an API endpoint whose caller happens to be probabilistic.

The probabilistic caller does not reduce the need for API discipline. It
increases it.

SignalDesk Commit 09 builds seven CDP tools as ordinary, deterministic Python
functions. There is no agent and no model-selected function call yet. The goal
is to establish the application boundary before testing whether a model can use
it.

## Start with the responsibility split

An agentic system has at least two different responsibilities:

```text
model
  interpret the question
  decide whether a tool is needed
  select a tool
  propose arguments
  use the returned evidence

application
  validate the proposed arguments
  authorize and bound data access
  execute deterministic code
  validate the result
  report errors
  control every side effect
```

Mixing these responsibilities creates magic functions: vaguely named
capabilities with hidden assumptions, broad access, and outputs that are hard
to verify. Separating them creates APIs that can be tested without a model.

Commit 09 implements only the application side. Commit 10 will measure the
model side.

## A tool contract has five parts

A usable tool needs more than a function name.

### 1. Purpose

The description must state one bounded capability. A model should not need to
guess whether a profile function also searches events or whether a recommendation
function contacts a customer.

### 2. Input schema

Inputs need types, required fields, enums, ranges, and limits. Unknown fields
should fail. A flexible dictionary is convenient for the implementer but
ambiguous for every caller.

### 3. Output schema

The result must be predictable enough for both application code and a model to
consume. It should include provenance and limitations when those affect how the
result may be used.

### 4. Error behavior

Invalid arguments, missing data, business conflicts, and unexpected failures
are different states. Returning stable error codes makes retries and model
behavior measurable.

### 5. Side effects

The contract must state whether the function only reads, creates a draft,
persists a record, or performs an external action. A harmless-sounding name is
not a safety mechanism.

SignalDesk's registry exposes these properties as JSON-compatible schemas and
declares every Commit 09 tool as `side_effects = none`.

## The seven SignalDesk tools

The layer covers the capabilities needed for a future retention workflow:

| Tool | What it does |
|---|---|
| `get_customer_profile` | Reads a bounded, PII-safe Customer 360 profile |
| `get_customer_events` | Reads identity-resolved events in a bounded window |
| `get_purchase_history` | Reads bounded orders and product-line evidence |
| `search_knowledge_base` | Searches current, approved policy documents |
| `calculate_customer_metrics` | Returns existing semantic-layer metrics |
| `get_campaign_eligibility` | Reports hard blocks or need for review |
| `create_retention_recommendation` | Constructs a non-persisted draft |

The names describe capabilities, but the schemas define their real meaning.

## Do not give the model a database

A generic SQL tool looks powerful because it can answer many questions. It
also transfers data-model knowledge, access control, query cost, privacy, and
failure handling to the least deterministic part of the system.

The SignalDesk tools expose domain-shaped reads instead:

```text
profile   -> selected Customer 360 attributes
events    -> resolved customer, 1-90 days, at most 100 rows
purchases -> 1-730 days, at most 50 orders
metrics   -> existing semantic features grouped by domain
knowledge -> current, approved documents, at most 10 results
```

SQL parameters are bound by application code. The caller cannot supply table
names, clauses, or arbitrary query text.

The profile omits raw email address, phone number, postal address, birth date,
and identity values. The relevant principle is data minimization:

> A tool should return the least data required to complete its declared job.

## Reproducible time is an API decision

"Events in the last 30 days" sounds deterministic until the reference time is
left implicit. Running the same call tomorrow would return a different slice.

SignalDesk anchors windows to the Customer 360 semantic `as_of_ts`. Given the
same warehouse and arguments, a call has the same meaning. The output also
returns its as-of value so downstream reasoning does not have to infer it.

This is a small example of a broader rule: determinism depends on making hidden
context explicit.

## Preserve the semantic layer

`calculate_customer_metrics` does not invent a new engagement score or churn
probability. It returns metrics that already exist in Customer 360, organized
into purchase, engagement, support, campaign, and subscription/consent
domains.

That constraint avoids a common failure mode. A helper function computes a
plausible-looking score, then the model treats it as an authoritative business
metric even though nobody defined, governed, or evaluated it.

Tools should reuse governed meanings before creating new ones.

## Retrieval is behind the interface

The knowledge-search tool currently uses a deterministic local lexical adapter
restricted to current and approved documents. Its output reports the method as
`lexical_current_approved`.

This does not overturn the Commit 08 vector-search result. Commit 08 compared
retrieval treatments. Commit 09 evaluates tool contracts and execution
behavior. Those are different experimental questions.

The tool interface can stay stable while a vector implementation replaces the
lexical adapter later:

```text
stable contract
  query
  optional policy families
  result limit
  authoritative document metadata

replaceable implementation
  lexical
  vector
  evaluated future treatment
```

An implementation change still has to earn adoption through retrieval and
tool-level evaluation.

## Eligibility should admit uncertainty

The warehouse can identify hard constraints such as an inactive customer or
missing channel consent. It cannot prove final campaign eligibility without a
specific campaign definition, audience rules, offer terms, and complete policy
interpretation.

The tool therefore returns only two decisions:

```text
BLOCKED
REVIEW_REQUIRED
```

It deliberately never returns `ELIGIBLE`.

This is not a missing feature. It is an honest contract. A customer having one
contactable channel means a later workflow may continue its review. It does not
mean an offer is approved for execution.

## "Create" must not imply execution

`create_retention_recommendation` is the highest-risk name in the layer. Its
output makes the boundary explicit:

```text
status                  = DRAFT
requires_human_approval = true
execution_allowed       = false
persisted               = false
```

The function creates an in-memory proposal, not a database row, campaign, or
customer communication.

The caller supplies evidence feature names and policy document IDs. Application
code attaches the actual Customer 360 values and verifies that each policy is
current and approved. The caller cannot fabricate the evidence values.

Authority validation still does not prove that a policy semantically supports
the recommendation. The result says so. Explicit limitations are part of the
output contract, not footnotes in documentation.

## Errors are normal tool outputs

A probabilistic caller will eventually propose malformed arguments. Invalid
calls are not exceptional edge cases in an agent system; they are part of the
normal operating distribution.

The registry converts failures into five stable codes:

| Code | Meaning |
|---|---|
| `VALIDATION_ERROR` | Arguments violate the schema |
| `NOT_FOUND` | Required customer or policy data is absent |
| `CONFLICT` | Request crosses a hard business boundary |
| `UNKNOWN_TOOL` | Function name is not registered |
| `INTERNAL_ERROR` | Unexpected execution failure |

The envelope does not expose a stack trace or database internals. Commit 10 can
now measure whether a model repairs a validation error, changes strategy after
a conflict, or stops after repeated failure.

## Measure functions before measuring agents

The frozen evaluation has 105 cases:

```text
7 tools x 10 valid cases   = 70
7 tools x 5 invalid cases  = 35
5 measured repetitions     = 525 executions
```

Invalid cases include malformed identifiers, unknown records, excessive
lookbacks, unsupported enum values, extra fields, an SQL-injection-like
identifier, unknown policies, duplicate evidence, short rationales, unsupported
actions, and blocked offers.

Every case is warmed before timing. Measured latency includes input validation,
execution, output validation, and construction of the result envelope. One-time
DuckDB connection and lexical-index construction are excluded.

The result:

| Tool | Valid success | Invalid behavior | p95 latency |
|---|---:|---:|---:|
| `calculate_customer_metrics` | 100% | 100% | 44.260 ms |
| `create_retention_recommendation` | 100% | 100% | 43.943 ms |
| `get_campaign_eligibility` | 100% | 100% | 44.134 ms |
| `get_customer_events` | 100% | 100% | 58.199 ms |
| `get_customer_profile` | 100% | 100% | 43.654 ms |
| `get_purchase_history` | 100% | 100% | 53.953 ms |
| `search_knowledge_base` | 100% | 100% | 4.596 ms |

The `src/tools` test suite has 96.05% combined line and branch coverage, above
the Commit 09 target of 80%.

## What these numbers do not prove

One hundred percent on frozen function cases does not mean the future agent is
correct. The benchmark does not test whether a model:

- recognizes when a tool is necessary,
- selects the right tool,
- constructs valid arguments on its first attempt,
- uses returned evidence correctly,
- avoids unnecessary calls,
- recovers from a tool error,
- or stops without taking an action.

It also does not establish lexical search as the best retrieval algorithm or
prove that the seven capabilities cover every CDP workflow.

The benchmark proves a narrower and necessary claim: for the frozen valid and
invalid calls, application behavior matches the declared contracts.

## The next experiment

Commit 10 can now introduce the first bounded agent. The model will receive the
same tool definitions that the deterministic tests exercised. The new
evaluation should measure tool selection, argument validity, unnecessary calls,
error recovery, evidence use, stopping behavior, latency, and cost.

The important architectural boundary remains unchanged:

```text
model proposes
application validates and executes
human or explicit policy authorizes consequential action
```

Building the tools first makes agent behavior observable. Without that layer,
an agent demo can look intelligent while hiding undefined access, inconsistent
errors, and accidental authority inside its functions.
