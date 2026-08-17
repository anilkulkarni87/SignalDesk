# Treating Prompts Like Software: Versioning, Evals, and Regressions

In the previous SignalDesk milestone, I made the first serious jump from
deterministic data engineering into probabilistic AI behavior.

I sent Customer 360 snapshots to an LLM.

I got strict structured output back.

I measured schema validity, classification accuracy, evidence coverage,
latency, tokens, and cost.

That was useful, but it left me with a new problem:

```text
How do I change a prompt without fooling myself?
```

Commit 05 was about that problem.

The goal was not to add RAG.

It was not to build an agent.

It was not to make the application more impressive.

The goal was much smaller and more important:

> Treat prompts like versioned software artifacts.

## Why a prompt needs a release process

Before this commit, SignalDesk had one main LLM prompt.

It consumed deterministic Customer 360 data and returned a structured risk
assessment.

That prompt had already been evaluated in Commit 04, but if I wanted to change
it, I needed a way to answer basic engineering questions:

```text
Did the new prompt improve behavior?
Did it break cases the old prompt handled correctly?
Did evidence coverage improve?
Did latency change?
Did token usage change?
Did cost change?
Which exact cases changed?
```

Those are normal questions for software.

But prompts often get edited casually.

Someone changes wording, runs a few examples, likes the answers, and ships it.

That is not engineering.

That is a demo loop.

For SignalDesk, I wanted a prompt change to earn adoption through measurement.

## Freezing V1

The first step was to freeze the old prompt.

I created:

```text
src/llm/prompt_versions/v1.py
```

That file is a copy of the released Commit 04 prompt.

It has a clear version name:

```text
commit04_v1_frozen
```

The word "frozen" matters.

V1 is the baseline.

It should not drift while I am testing V2.

If I change both prompts while comparing them, the experiment loses meaning.

## Creating V2 as a placeholder

Then I created:

```text
src/llm/prompt_versions/v2.py
```

But I did not immediately improve it.

At first, V2 was behaviorally identical to V1.

That might seem pointless, but it was deliberate.

It gave the harness a candidate prompt to run while forcing a useful discipline:

```text
Do not write Prompt V2 until V1 failures are measured on a fixed eval suite.
```

Without that rule, I would be guessing.

With that rule, V2 had to be tied to an observed failure mode.

## The first comparison was not proof

The first 50-case Commit 05 run produced a V1 versus V2 comparison.

At first glance, that looked like progress.

There was a report.

There were metrics.

There were apparent improvements.

But review exposed two problems.

First, V2 was still a placeholder. It had no behavioral change.

Second, the new Commit 05 case selector had weakened the cleaner safeguards from
Commit 04's second evaluation rubric.

Some cases had ambiguous broader warning evidence.

One multi-warning case even omitted `support_attention_flag` from required
evidence.

So the correct conclusion was not:

```text
V2 improved.
```

The correct conclusion was:

```text
This run is a repeatability experiment, not proof of prompt improvement.
```

That distinction matters.

A comparison report can look rigorous while measuring the wrong thing.

## Fixing the cases before fixing the prompt

In Commit 04, I learned that bad evaluation cases can make good model behavior
look wrong.

Commit 05 repeated that lesson.

Before tuning the prompt, I regenerated the 50-case suite using the cleaner
Commit 04 v2 selectors.

The suite covered five categories:

```text
10 multiple warning signal cases
10 purchase decline only cases
10 engagement decline only cases
10 support attention only cases
10 no warning signal cases
```

The selectors intentionally avoided contradictory broader evidence.

For example, a "support attention only" case could not also have purchase
decline, engagement decline, dormant purchase behavior, high-priority support
issues, heavy negative support volume, refunds, or recent subscription
cancellation.

A LOW case had to actually look low across the broader Customer 360 snapshot,
not merely have three Boolean flags set to false.

The regenerated suite passed local validation:

```text
cases: 50
counts: 10 per category
selector violations: 0
```

Only after that did the prompt experiment become meaningful.

## Measuring V1 on the fixed suite

I ran frozen V1 with the same model and reasoning setting from Commit 04:

```text
model = gpt-5.6-luna
reasoning = none
```

The result:

```text
API success:              100%
schema validity:          100%
evidence feature validity: 100%
risk accuracy:             86%
required evidence:         78%
reasoning tokens:           0
```

The failures were not random.

They clustered in two places.

First, V1 under-classified some customers with both `purchase_decline_flag` and
`engagement_decline_flag`.

Those customers were expected to be HIGH risk under the rubric, but V1 sometimes
returned MEDIUM.

Second, V1 sometimes reached the right risk label while omitting the exact true
warning flag from its evidence list.

That is an important product issue.

In SignalDesk, evidence is not decoration.

A human reviewer should be able to see which deterministic Customer 360 facts
support the model's conclusion.

## Writing a real V2 hypothesis

Now V2 had a job.

It was not "make the prompt better."

It was:

```text
V1 under-classified customers with both purchase_decline_flag and
engagement_decline_flag set, and sometimes omitted true warning flags from
evidence. V2 should improve HIGH classification for multiple warning signals
and required-evidence coverage by making the three curated warning flags
explicit decision anchors.
```

That hypothesis produced a small prompt change.

V2 made the curated warning flags explicit:

```text
purchase_decline_flag
engagement_decline_flag
support_attention_flag
```

It told the model to cite true warning flags when they influence the assessment.

It also calibrated the risk labels:

```text
purchase decline + another warning flag -> HIGH
exactly one curated warning flag -> MEDIUM
no curated warning flags and no other material warning -> LOW
```

This was not a broad rewrite.

It was a targeted fix for measured failures.

## Comparing V1 and V2

Then I ran V2 against the same 50 cases.

Same model.

Same reasoning setting.

Same schema.

Same Customer 360 inputs.

The result:

```text
V1 risk accuracy:      86%
V2 risk accuracy:     100%
delta:                +14 points

V1 required evidence:  78%
V2 required evidence: 100%
delta:                +22 points

regressions:             0
improvements:           16
schema validity:       100% both
reasoning tokens:        0 both
```

The cost changed slightly:

```text
mean input tokens:   +139
mean output tokens:  -4.3
mean cost/request:   +$0.000113
```

That is the kind of tradeoff I can reason about.

V2 used more prompt text, so input tokens increased.

But it fixed the measured behavior, improved evidence coverage, and introduced
zero observed regressions on this suite.

For this commit, V2 earned adoption.

## Why regression count changed how I think

Average accuracy is not enough.

A new prompt can improve the average while breaking important cases that the old
prompt handled correctly.

That is why the comparison report tracks regressions explicitly.

For this run:

```text
regressions = 0
```

That single number matters as much as the headline accuracy improvement.

It turns the decision from:

```text
V2 looks better.
```

into:

```text
V2 improved 16 cases and did not regress any observed cases in the fixed suite.
```

That is a much stronger engineering statement.

## What Commit 05 actually proved

Commit 05 did not prove that SignalDesk predicts churn in the real world.

It did not prove the prompt will generalize to every future customer.

It did not add policies, retrieval, tools, or agents.

It proved something narrower:

```text
Given this fixed Customer 360 evaluation suite, Prompt V2 improves measured
risk classification and required-evidence coverage over frozen V1 without
observed regressions.
```

That is enough for this milestone.

The learning journey is moving in layers:

```text
deterministic Customer 360
strict LLM output
behavioral evaluation
prompt versioning
regression comparison
```

Only after those foundations are reliable does it make sense to add more complex
AI system behavior.

## The lesson I am carrying forward

The biggest lesson from Commit 05 is that prompt engineering should feel less
like copywriting and more like software release management.

A prompt needs:

```text
versioning
baselines
fixed test cases
hypotheses
metrics
regression checks
cost measurements
adoption decisions
```

The prompt text matters.

But the process around the prompt matters just as much.

That is the difference between an AI demo and an AI engineering system.
