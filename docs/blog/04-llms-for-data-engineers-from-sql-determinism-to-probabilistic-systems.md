# LLMs for Data Engineers: From SQL Determinism to Probabilistic Systems

For the first three SignalDesk milestones, almost everything behaved like the systems I already knew as a data engineer.

If my SQL transformation was correct, the same input produced the same output.

If a Customer 360 test passed today, I could expect the exact same calculation to pass tomorrow given the same data and `as_of` timestamp.

Then I introduced an LLM.

That changed the engineering model.

Not because the API was difficult to call.

The hard part was learning what it means to build software when a successful request and a valid response still do not guarantee the behavior I expected.

## Starting with deterministic facts

Before introducing the LLM, SignalDesk already had a deterministic Customer 360.

For a customer, I could calculate things such as:

```text
orders_60d
orders_prior_60d
sessions_60d
sessions_prior_60d
refund_rate_90d
open_support_cases
email_open_rate_90d
```

Those values belonged in SQL.

I did not want the model estimating how many orders a customer placed or inferring whether session activity had declined.

That gave me an important architecture boundary:

```text
deterministic system
    calculates facts

probabilistic system
    interprets facts
```

The LLM could decide that `orders_60d` mattered.

It could explain why it mattered.

But the actual value still came from Customer 360.

That meant the model was responsible for interpretation, not arithmetic truth.

## My first model call was deliberately boring

I did not start with RAG.

I did not start with LangGraph.

I did not give the model tools.

I sent one Customer 360 JSON document to the OpenAI Responses API and asked for a strict structured assessment.

The output contained:

```text
risk_level
summary
evidence
recommended_investigation
limitations
```

The first request worked.

It returned valid structured output, took about 5.4 seconds, used 1,432 total tokens, and cost roughly $0.0033.

That was useful.

But one successful request did not tell me whether the system was reliable.

So I built an evaluation set.

## A valid response can still be wrong

I generated 30 Customer 360 examples across five scenarios:

```text
multiple warning signals
purchase decline only
engagement decline only
support attention only
no warning signals
```

The first evaluation looked promising from a software perspective:

```text
API success          100%
schema validity      100%
evidence-key validity 100%
```

Nothing crashed.

Every response matched the schema.

The model never referenced a nonexistent Customer 360 feature.

But agreement with my expected risk labels was only:

**83.33%**

This was my first clear lesson in probabilistic engineering:

> A valid response is not the same thing as a correct response.

With SQL, a test often tells me whether a transformation is right or wrong.

With an LLM, I also have to define what "right" means.

That turned out to be harder than expected.

## The model was not the only thing that could be wrong

I manually reviewed the five disagreements.

One case was labeled as a medium-risk "support-only" customer.

But the model saw:

```text
220 days since purchase
2 open support cases
1 negative support case
1 high-priority support case
```

It classified the customer as HIGH.

Another expected-MEDIUM case had:

```text
195 days since purchase
100% recent refund activity
2 open cases
3 negative support cases
low CSAT
customer status = PAUSED
```

The model again returned HIGH.

That was not obviously a model failure.

My evaluation case was poorly labeled.

The first rubric had classified customers primarily from three flags:

```text
purchase_decline_flag
engagement_decline_flag
support_attention_flag
```

But the model saw dozens of features.

I was evaluating one decision function while asking the model to use another.

So instead of changing the prompt, I fixed the evaluation.

That was probably the most useful lesson of the entire commit:

> Gold labels are software too.

They need design, testing, review, and versioning.

## The second evaluation was cleaner

I created a V2 evaluation set.

The LOW cases were actually low across the broader snapshot.

The support-only cases excluded strong unrelated warning signals.

The HIGH cases contained multiple material signals rather than simply two Boolean flags.

I kept the model and prompt unchanged.

The result improved to:

```text
V2 rubric agreement        90%
API success               100%
schema validity           100%
evidence-feature validity 100%
```

Now I had a baseline I trusted much more.

But another metric exposed a new problem.

Required evidence coverage was only:

**76.67%**

The model often reached the expected conclusion while omitting some evidence that I wanted a reviewer to see.

That created another useful distinction:

> A correct conclusion does not guarantee a complete evidence trail.

For SignalDesk, that matters.

A Retention Specialist should be able to inspect why the system reached a conclusion rather than accept a classification from a black box.

## Structured output did not solve semantic quality

Strict output schemas were extremely useful.

They gave me predictable response objects and prevented arbitrary evidence fields.

But the experiment showed what structured output does and does not guarantee.

It can guarantee:

```text
field names
types
allowed values
response shape
```

It cannot guarantee:

```text
correct reasoning
correct classification
complete evidence
good business judgment
```

That separation is easy to miss when an application demo always returns perfectly formatted JSON.

## Then I tested more reasoning

Once I had a trustworthy V2 evaluation set, I changed exactly one variable.

Baseline:

```text
gpt-5.6-luna
reasoning = none
```

Experiment:

```text
gpt-5.6-luna
reasoning = low
```

Same 30 customers.

Same prompt.

Same output schema.

Same rubric.

I expected that additional reasoning might improve classification or evidence completeness.

It did not.

Both configurations achieved:

**90% rubric agreement**

But `reasoning=low` consumed:

**1,426 additional reasoning tokens**

across the 30 requests.

It also produced:

```text
required evidence:
76.67% → 66.67%

mean latency:
3.35s → 3.58s

p95 latency:
4.03s → 4.39s

mean output tokens:
392.5 → 436.43

mean cost/request:
$0.00340 → $0.00367
```

So the more expensive configuration gave me no classification improvement and worse evidence completeness.

The decision was straightforward:

```text
gpt-5.6-luna
reasoning = none
```

for this workload.

## More reasoning is not automatically better

Before this experiment, I could easily have assumed:

> More model reasoning should improve the result.

That is not a useful engineering assumption.

The better question is:

> Does additional reasoning improve this particular task enough to justify its latency and cost?

For this task, the answer was no.

That does not mean reasoning tokens are useless.

It means they are another engineering resource that should be justified with measurement.

## The mental shift from data engineering

This commit changed how I think about correctness.

In the Customer 360 pipeline, I had:

```text
33 deterministic tests
33 passes
```

With the LLM I had:

```text
30 successful API calls
30 valid schemas
27 classifications matching the V2 rubric
```

Nothing crashed.

The code worked.

The schema worked.

But the system still behaved differently from my expectation in some cases.

That is the shift from deterministic to probabilistic engineering.

Traditional tests still matter.

But they are not enough.

I now also need:

```text
evaluation cases
rubrics
behavioral metrics
failure analysis
latency measurements
token measurements
cost measurements
```

And I need to question the evaluation itself when results look wrong.

## What I am carrying forward

Commit 04 did not build an impressive AI agent.

That was intentional.

It taught me the primitive I will eventually put inside an agent.

I now have a measured LLM component that:

- consumes deterministic Customer 360 data,
- returns strict structured output,
- tracks retries, latency, tokens, and cost,
- supports streaming,
- runs against a versioned evaluation set,
- achieves 90% agreement with the current V2 rubric,
- keeps deterministic customer values outside model ownership,
- uses `reasoning=none` because measurement showed that extra reasoning did not help.

The next step is not RAG yet.

The next step is to make the evaluation system itself more rigorous: versioned prompts, larger golden datasets, regression comparisons, and repeatable experiment reports.

That is where an LLM demo starts becoming an engineering system.
