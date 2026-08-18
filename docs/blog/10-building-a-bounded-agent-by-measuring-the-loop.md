# Building a Bounded Agent by Measuring the Loop

An agent is often described as a model that can use tools. That description
hides the engineering work.

A model does not execute a function because it understands the database or owns
the application. It emits a tool name and arguments. Application code decides
whether that tool is available, whether the arguments are valid, what data may
be read, what result is returned, and when the loop must stop.

That leads to a more useful first principle:

> An agent is a probabilistic decision loop inside deterministic boundaries.

SignalDesk Commit 10 builds that loop directly over the read-only CDP tools from
Commit 09. The goal is not production autonomy. The goal is to make each model
decision observable enough to evaluate.

## The primitive loop

The implementation deliberately does not start with an agent framework. It
uses the Responses API and carries each function call and result into the next
model request explicitly:

```text
customer question
       |
       v
model chooses a tool and arguments
       |
       v
application validates subject and schema
       |
       v
deterministic tool executes
       |
       v
result returns to the model
       |
       +-- another tool call
       |
       +-- typed final answer
```

The model owns interpretation, tool choice, argument proposal, evidence
selection, and stopping. Application code owns the allowlist, customer binding,
validation, deterministic execution, retries, call limits, and final schema.

The model never receives SQL access.

## Reduce authority before measuring intelligence

The agent receives six read-only tools:

```text
get_customer_profile
get_customer_events
get_purchase_history
search_knowledge_base
calculate_customer_metrics
get_campaign_eligibility
```

The recommendation-draft tool is intentionally absent. No available function
can persist a recommendation, contact a customer, execute a campaign, issue an
offer, or modify the warehouse.

Every customer-scoped call must use the task's customer ID. A call for another
customer fails before execution. Event and purchase reads are bounded.
Knowledge search returns only current, approved documents. Model rounds and
tool calls have hard limits.

These constraints are not evidence that the model is trustworthy. They reduce
the consequences when it is not.

## Evaluate decisions separately

An average task score is too coarse for an agent. A final answer can be correct
after an unnecessary call. A citation can name a retrieved document without
exposing the text used. A summary can reach the right conclusion while omitting
the decisive feature.

The Commit 10 harness therefore measures:

```text
correct tools selected
correct arguments
unnecessary calls
correct conclusion
complete concise summary
all evidence grounded
required evidence present
all cited policies retrieved
all cited policy IDs and excerpts evidenced
required policy families cited
task completion
```

Efficiency is separate from completion. That decision matters later: the final
run contains one repeated tool call but no correctness failure.

## Freeze a task matrix

The evaluation uses 50 distinct customers and six task categories:

| Task | Cases | Capability under test |
|---|---:|---|
| Multi-signal investigation | 10 | Coordinate metrics, purchases, and events |
| Purchase investigation | 10 | Explain purchase decline from metrics and history |
| Behavior investigation | 10 | Explain engagement decline from metrics and events |
| Support-policy investigation | 10 | Separate customer evidence from support policy |
| Profile lookup | 5 | Use only the profile capability |
| Campaign readiness | 5 | Combine eligibility, campaign policy, and consent policy |

The same model, `gpt-5.6-luna`, runs with reasoning set to `none` throughout the
comparison. Frozen cases prevent prompt changes from quietly changing the
questions being answered.

## Treat each prompt version as a hypothesis

The prompt reached V4, but these were not four rounds of subjective
wordsmithing. Each change followed a measured failure.

### V1: expose the loop

The first six-task pilot established model-controlled tool calls and structured
termination. It also revealed an evaluator error: exact dotted evidence paths
were being flattened. Evaluation code can be wrong even when model behavior is
right.

### V2: fix paths, query decomposition, and summary bounds

V2 used canonical JSON paths, one policy-family intent per search, and a
300-character complete-summary limit.

The full run selected correct tools, constructed correct arguments, and reached
the correct conclusion on every task. Completion was still 80% under the
historical rubric.

Trace review found four distinct causes:

```text
decisive flags omitted after all 10 evidence slots were filled
bounded event samples interpreted as failed investigations
unnecessary profile calls in support investigations
citations checked for retrieval membership but not evidence use
```

One broad instruction such as "be more grounded" would not define which
behavior should change.

### V3: prioritize evidence and define completion

V3 required conclusion-defining flags before secondary evidence, treated
successful bounded samples as limitations rather than failures, reserved
profile calls for profile questions, and required exact policy IDs and excerpts
for every citation.

It fixed every original non-campaign failure and every support-policy task. All
five campaign tasks still failed.

The pattern was consistent: campaign answers filled all 10 evidence slots with
channel details. The cited campaign and consent evidence no longer fit.

### V4: allocate the evidence budget explicitly

V4 did not enlarge the schema or weaken the evaluator. It reserved five slots
before optional channel details:

```text
overall eligibility status
campaign policy ID
campaign policy excerpt
consent policy ID
consent policy excerpt
```

At most two channel details may follow. Every targeted campaign answer used
seven evidence items and passed.

The lesson is broader than this prompt:

> Output limits are allocation constraints, not merely size constraints.

If every item has equal priority, verbose secondary details can crowd out the
facts needed to prove the conclusion.

## Compare with the same evaluator

The citation requirement became stricter during the experiment. Comparing the
historical V2 completion rate directly with V4 would mix prompt improvement and
metric change.

I regraded the stored V2 outputs with the V4 evaluator without making another
model call:

| Metric | V2 regraded | V4 full |
|---|---:|---:|
| Correct tools | 100% | 100% |
| Correct arguments | 100% | 100% |
| Unnecessary-tools empty | 96% | 98% |
| Correct conclusion | 100% | 100% |
| Required evidence present | 86% | 100% |
| Policy citations evidenced | 70% | 100% |
| Policy-task completion | 0% | 100% |
| Overall task completion | 50% | 100% |

The original V2 report remains preserved with its historical 80% completion
score. Regrading changes the comparison, not the record of what was measured at
the time.

## The final run

V4 completed all 50 frozen tasks:

```text
API success                    = 100%
correct tools                  = 100%
correct arguments              = 100%
correct conclusions            = 100%
required evidence              = 100%
policy citations evidenced     = 100%
required policy families       = 100%
task completion                = 100%
unnecessary-tools empty        = 98%
```

Operationally:

```text
mean / p50 / p95 latency = 6.0616 / 5.4742 / 9.2174 seconds
tool calls                = 111
API requests              = 106
retry attempts            = 0
input / output tokens     = 302,870 / 22,966
estimated cost            = $0.236846
```

Relative to V2, V4 reduced mean latency by 12%, p95 latency by 31%, output
tokens by 17%, and estimated cost by 8%. Input tokens increased by 24% because
the accepted instructions are more explicit.

One purchase task repeated `calculate_customer_metrics` with identical
arguments. Creating V5 to eliminate one stochastic repeat would optimize
against the benchmark rather than teach a new behavior.

## What 100% does not mean

The final number has three important limits.

First, exact citation evidence proves provenance, not semantic entailment.
Seventeen of 20 cited excerpts use the same generic uncertainty and escalation
passage. The system can prove where the text came from and its policy family,
but not that it is the most specific support available.

Second, the frozen cases became the development regression suite. V3 and V4
were designed from their failures. The final run proves conformance to that
suite, not expected accuracy on unseen questions.

Third, this is one stochastic run. A repeat could produce a different
unnecessary call or evidence choice with the same model, prompt, and inputs.

There is also no write-capable tool, durable workflow state, human approval
step, or customer action. Those omissions are the point of this milestone.

## What I learned

1. Agent quality is a vector of behaviors, not one accuracy number.
2. Deterministic tools make probabilistic decisions inspectable.
3. A bounded successful sample can support a completed task while remaining an
   explicit limitation.
4. Citation membership, exact citation evidence, and semantic support are
   different claims.
5. Evidence schemas need priority rules when facts compete for a fixed budget.
6. Regrading stored outputs is necessary when the evaluator becomes stricter.
7. A regression suite is evidence of conformance, not a holdout estimate.
8. Not every stochastic inefficiency deserves another prompt version.

## The next boundary

Commit 10 proves the primitive model-tool loop over frozen tasks. The next step
can add explicit workflow state and framework orchestration while preserving
the same responsibility split:

```text
model proposes
application validates and executes
evaluation determines whether behavior earned adoption
```

An orchestration framework can make state and transitions easier to manage. It
does not replace tool contracts, evidence grounding, or behavioral evaluation.
