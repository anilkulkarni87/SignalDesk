# Commit 07: The Right Document Is Not Yet a Grounded Answer

Commit 06 answered one question:

> Can semantic search retrieve the right NovaCart knowledge?

On 50 frozen retrieval queries, vector Recall@5 reached 98% and materially beat
the lexical baseline.

Commit 07 asks the next question:

> After retrieving the right evidence, can the model use all relevant policy,
> attribute citations correctly, and avoid unsupported claims?

That is a different system problem.

## The RAG boundary

The first version is deliberately bounded:

```text
explicit user question
  + deterministic Customer 360 snapshot
  -> deterministic policy query planner
  -> text-embedding-3-small
  -> pgvector retrieval
  -> CURRENT + APPROVED filtering
  -> bounded policy context
  -> gpt-5.6-luna, reasoning=none
  -> structured assessment
```

There is no agent loop. The model does not decide which tools to call, update a
customer account, send a message, or execute a retention intervention.

Customer facts and policy facts also remain separate:

```text
Customer 360 says what is observable about the customer.
Retrieved policy says what process and constraints apply.
```

## One hundred questions, fifty customers

Commit 07 reuses the 50 clean Commit 05 customers. Each customer receives two
questions:

1. Why is retention risk at its current level, and what should be investigated?
2. Which policy constraints and known gaps should shape a recommendation?

This creates 100 questions, not 100 independent customer profiles.

The cases freeze:

- expected risk,
- required Customer 360 evidence,
- deterministic policy queries,
- required policy families,
- required known-gap documents.

The generation model never receives the gold answer labels.

## Retrieval passed before generation ran

The retrieval gate ran all 100 questions without calling the generation model.
Every case received the expected current approved documents and policy families
inside the 16,000-character context budget.

```text
retrieval gate = 100 / 100
```

That result matters because it establishes ownership of later failures. If the
right policy reached the prompt but the answer did not cite it, the failure is
in generation or in the generation contract, not vector search.

## The five-case smoke test was misleading

The first five generated answers scored 100% on every measured field.

That proved the API call, schema, retrieval connection, and metric pipeline
worked. It did not prove behavior across the full corpus.

The full run found the variation the smoke test could not reveal.

## The first full result

The first V3 run produced:

```text
questions                              = 100
successful API calls                   = 98
risk correctness                       = 100% of successful calls
answer correctness                     = 100% of successful calls
expected policy-family citation        = 75.51%
exact excerpt grounding, case rate     = 83.67%
exact excerpt precision per citation   = 95.17%
unsupported policy claims empty        = 97.96%
reasoning tokens                        = 0
estimated generation cost              = $0.758971
```

The customer-risk behavior was strong. Retrieval remained strong. The citation
contract was not strong enough.

## What actually failed

Two requests timed out.

Across the 98 successful responses, 24 omitted at least one policy family that
the customer-derived planner identified as relevant. Consent, offer eligibility,
causal-governance gaps, and subscription constraints were the common omissions.

There were also 18 invalid excerpts across 16 responses:

- 12 were real text from another retrieved near-duplicate document,
- 6 contained malformed trailing control characters.

The model often knew the policy sentence but attached it to the wrong source.
That distinction explains an initially confusing pair of metrics:

```text
all cited document IDs were retrieved = 100%
all excerpts belonged to those IDs    = 83.67% of cases
```

The document was present, but the quote did not belong to that document.

Two responses also returned:

```json
{"unsupported_policy_claims":[""]}
```

That exposed a schema defect: the list length was constrained, but each string
was not required to contain text.

## Why another prompt instruction is not enough

The V3 prompt already told the model to copy an exact excerpt.

Repeating that instruction more forcefully would still leave byte-level source
integrity under probabilistic control. A language model is useful for selecting
and interpreting evidence. It should not own an invariant that application code
can enforce deterministically.

So V4 changes the interface:

```text
retrieved source text
  -> deterministic quote spans
  -> stable quote IDs
  -> model selects quote IDs
  -> application resolves document ID and exact excerpt
```

The model can no longer combine a sentence from one document with another
document ID. Unknown quote IDs fail local validation.

Exact quotation becomes a transport invariant. Whether the selected quote is
semantically useful remains an evaluation question.

## Policy intent must also be explicit

V3 told the model to cite guidance when it used guidance. The evaluation expected
every customer-derived policy intent to be considered.

V4 exposes those runtime intents directly:

```text
support warning       -> support policy
channel opt-out       -> consent policy
behavior decline      -> retention and offer policy
discount reasoning    -> causal-governance gap
recent cancellation   -> subscription policy
```

These are not leaked gold labels. They are the production planner output that
already determined which searches ran.

For every intent with an available source, the model must select a relevant
quote. If an intent has no authoritative source, it must record the gap rather
than invent guidance.

## Reliability without hiding instability

V4 also adds bounded retries for transient timeouts, rate limits, connection
errors, and server errors.

The report keeps two measures:

```text
first-attempt API success
eventual API success after bounded retries
```

This lets the system become more reliable without rewriting history about the
service's first-attempt behavior.

## The next experiment

The V3 result remains frozen as the baseline. The 100 questions, labels,
retrieval settings, context budget, model, and reasoning setting remain fixed.

V4 has one predeclared hypothesis:

> Deterministic quote IDs will eliminate malformed and cross-attributed
> citations, while explicit planner-intent coverage will raise expected-family
> citation above 90% without reducing customer-answer correctness.

First, ten cases representing the observed failure classes will test whether the
mechanism works. Then all 100 frozen questions will run again, and per-case
improvements and regressions will be compared.

The first cohort attempt produced another evaluation lesson. All ten API calls
returned, but nine outputs ended partway through the structured JSON. Counting
those as successful generation would have confused transport success with a
usable model result. The runner now gives generation an explicit output budget,
retries incomplete responses, and reports first-attempt versus eventual success.
It also asks for one strongest quote per required family after the one valid case
selected eight quotes for a single family. The cohort must run again before the
V4 hypothesis can be judged.

The second attempt made the failure observable: four responses completed and
passed every metric, while six exhausted three attempts with
`max_output_tokens`. Their raw text consistently stopped while choosing a long
quote identifier. The quote catalog now exposes short request-local IDs such as
`Q001`; the application still resolves each ID to its exact document, chunk, and
text. This preserves deterministic grounding while simplifying the constrained
structured-output choice.

The third attempt completed all ten cases and achieved 100% answer correctness,
schema validity, citation resolution, exact excerpts, and unsupported-claim
avoidance. Policy-family coverage remained 80%. Two answers spent all six flat
citation slots on duplicate retention, offer, and consent evidence while
omitting the causal-governance gap.

That exposed a second design principle: a prompt request is weaker than a schema
invariant. V5 makes every planner intent a required output field and restricts
that field's quote choices to sources valid for the intent. The next cohort run
tests whether structural intent coverage clears the 90% target without harming
the behavior V4 already fixed.

V5 reached 100% document and family coverage, but one answer converted "causal
benefit cannot be inferred" into "no causal benefit." Those statements are not
equivalent: missing causal evidence does not prove zero effect. The model even
self-reported the overstatement as unsupported. V6 preserves the metric and adds
a narrow calibration rule for unknown versus zero effect before the final full
run.

V6 passed all ten targeted cases with 100% first-attempt API success, answer
correctness, intent coverage, exact citation grounding, and unsupported-claim
avoidance. The V5-to-V6 comparison recorded one improvement and no regressions.
That clears the targeted gate, but the claim still has to survive the frozen
100-question run before Commit 07 is complete.

## The final result

V6 passed the live retrieval gate and all 100 frozen generation questions:

```text
API and schema validity             = 100%
answer correctness                  = 100%
expected policy-family citation     = 100%
exact citation grounding            = 100%
unsupported claims empty            = 100%
reasoning tokens                     = 0
mean total latency                   = 5.5025 seconds
estimated generation cost           = $0.637756
```

The V3-to-V6 comparison found no tracked regressions. Exact grounded excerpts
improved from 82 to 100 cases, and expected-family citation improved from 74 to
100 cases. Mean latency and cost per successful answer also fell even though the
intent-keyed input schema used more tokens.

## What 100% still does not mean

The final metrics prove the contracts they actually measure. They do not prove
that every prose clause is semantically entailed by its selected quote.

A manual audit found nine conservative statements that causal benefit was "not
established" in cases without a retrieved governance source. This is safer than
claiming zero effect, but "the retrieved context does not establish causal
benefit" would be more precise. Exact citation transport and semantic citation
quality are separate evaluation problems.

That is the final Commit 07 lesson:

```text
retrieve the right evidence
  -> require every policy intent
  -> resolve citation identity deterministically
  -> calibrate generated claims
  -> measure the remaining semantic gap honestly
```

V6 is adopted for Commit 07. The system remains recommendation-only, with human
review and no agent or automatic execution.

That is the larger lesson of Commit 07:

```text
RAG quality is not one score.

It is a chain of independently testable contracts:
retrieval, authority, context inclusion, answer correctness,
policy coverage, citation identity, unsupported claims, and reliability.
```
