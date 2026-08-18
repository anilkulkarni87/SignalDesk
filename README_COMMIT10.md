# SignalDesk Commit 10 - Single-Agent Customer Investigator

Commit 10 introduces the first model-controlled loop in SignalDesk. The model
may decide whether to query profile, metrics, events, purchase history, policy,
or campaign readiness. Application code still validates and executes every
call.

The architecture is deliberately implemented without LangGraph or an agent
SDK. Commit 10 learns the primitive agent loop before Commit 11 adds a workflow
framework.

## Responsibility boundary

```text
model
  interpret one customer question
  select a read-only tool
  construct arguments
  decide whether more evidence is needed
  return a structured conclusion

application
  expose only approved tools
  bind calls to the task customer
  validate every argument
  execute deterministic Python
  return structured success or error results
  enforce round and call limits
  validate the final answer
```

The model never receives database access.

## Exposed tools

The agent receives six Commit 09 tools:

```text
get_customer_profile
get_customer_events
get_purchase_history
search_knowledge_base
calculate_customer_metrics
get_campaign_eligibility
```

`create_retention_recommendation` is deliberately excluded. Customer actions,
draft creation, persistence, and approval workflows remain outside Commit 10.

## Bounded loop

The loop is implemented in `src/agent/investigator.py`:

```text
user task
   |
   v
Responses API
   |
   +-- final structured answer --> validate --> finish
   |
   +-- function call
           |
           v
      subject binding
           |
           v
      Commit 09 registry validation
           |
           v
      deterministic tool execution
           |
           v
      function_call_output --> next model round
```

The transcript is carried explicitly between Responses API calls while
`store=False`. Customer investigation state is not stored by the API.

Hard limits:

```text
model rounds     <= 8
tool calls       <= 8
event rows       <= 10 for evaluated tasks
purchase orders  <= 10 for evaluated tasks
reasoning effort = none
model            = gpt-5.6-luna
```

## Security and execution controls

### Subject binding

Every customer-scoped tool argument must match the customer in the task. A
model-generated request for another customer is blocked with `CONFLICT` before
the tool registry executes it.

### Tool output is data

The system prompt tells the model that tool output is untrusted data, not
instructions. This is important for retrieved documents and prepares for later
prompt-injection testing.

### No consequential action

No exposed tool can contact a customer, execute a campaign, issue an offer,
write a CDP event, or persist a recommendation.

### Structured termination

The model must stop with a strict `InvestigationAnswer` containing:

```text
customer_id
task_status
conclusion_code
risk_level
summary
evidence
policy_document_ids
limitations
```

Every evidence item names its source tool, field, exact scalar value, and
interpretation. Local Pydantic validation rejects an invalid final shape.

## Frozen 50-task evaluation

`evals/commit10/cases.jsonl` uses 50 distinct customers from the clean Commit
05 cohort:

| Task type | Cases | Required capability |
|---|---:|---|
| Multi-signal investigation | 10 | Metrics, purchases, events |
| Purchase investigation | 10 | Metrics, purchases |
| Behavior investigation | 10 | Metrics, events |
| Support-policy investigation | 10 | Metrics, support knowledge |
| Profile lookup | 5 | Profile only |
| Campaign readiness | 5 | Readiness, campaign and consent knowledge |

The runner rejects changed case counts, duplicate case IDs, duplicate customer
subjects, unexpected task distributions, or incomplete tool rubrics.

## Metrics

The harness scores these separately:

```text
correct tools selected
correct tool arguments
unnecessary tools empty
correct conclusion
complete concise summary
all evidence grounded
required evidence present
all policy citations retrieved
all policy citations evidenced by exact document ID and excerpt
required policy families cited
task completion
```

Task completion requires successful required tools, valid arguments, the
expected conclusion, grounded evidence, and required policy support. It does
not require the unnecessary-tools metric to pass, so efficiency remains visible
instead of being hidden inside correctness.

Operational measurements include:

```text
model rounds
tool calls per task
API requests and retry attempts
latency p50 and p95
input and output tokens
estimated cost per task
```

## Generate and test

```bash
python -m pip install -r requirements-commit10.txt
python -m evals.commit10.make_cases
python -m unittest discover -s tests -v
```

## Cross-category smoke test

Make the API key available in the same terminal, then run one task from each
category:

```bash
export OPENAI_API_KEY="..."

python -m evals.commit10.runner \
  --case-id agent_multiple_warning_signals_01 \
  --case-id agent_purchase_decline_only_01 \
  --case-id agent_engagement_decline_only_01 \
  --case-id agent_support_attention_only_01 \
  --case-id agent_profile_01 \
  --case-id agent_campaign_06 \
  --results evals/commit10/reports/pilot_v4_smoke_results.jsonl \
  --report evals/commit10/reports/pilot_v4_smoke_report.json
```

Inspect the pilot report and individual traces before changing the prompt or
running all 50 tasks. A pilot failure should become a specific hypothesis, not
an unmeasured prompt rewrite.

## Pilot V1 finding

The first six-task pilot is preserved in `pilot_results.jsonl` and
`pilot_report.json`. It established:

```text
API success                 = 100%
correct tools selected      = 100%
correct tool arguments      = 100%
no unnecessary tools        = 100%
correct conclusions         = 100%
reported task completion    = 33.33%
```

Trace review found three causes behind the low completion score:

1. Four answers used precise dotted fields such as
   `purchase.purchase_decline_flag`, but the V1 evaluator flattened paths to
   leaf names. Those grounding failures were evaluator false negatives.
2. The campaign task searched campaign and consent policy together. Ranking
   returned five campaign documents and no consent document. This is the
   cross-family query-decomposition failure already identified in Commit 08.
3. Three summaries used exactly the 600-character schema maximum and ended
   mid-sentence.

V2 makes a measured hypothesis rather than weakening the checks:

```text
canonical evidence paths
+ one policy family per search
+ summary <=300 characters with terminal punctuation
= grounded, complete answers without tool-selection regressions
```

The V2 pilot writes separate files so V1 remains a repeatable baseline.

## Full V2 finding and V3 hypothesis

The preserved 50-task V2 run reached 100% for API success, tool selection,
arguments, conclusions, concise summaries, and scalar evidence grounding. It
also exposed three narrower problems:

```text
required evidence present = 86%
task completion           = 80%
unnecessary tools empty   = 96%
```

All seven required-evidence misses used the 10-item evidence maximum and
omitted `engagement.engagement_decline_flag`. Six tasks returned `LIMITED`
solely because a successful 10-row event sample reported `truncated=true`.
Two support tasks made an unnecessary profile call.

The original policy metric also proved only that cited IDs appeared somewhere
in retrieval results. It did not prove that the answer exposed the exact source
text used. V3 therefore tests one focused hypothesis:

```text
decisive flags first
+ expected sample truncation recorded as a limitation
+ profile lookup reserved for profile questions
+ one cited policy per family with exact ID and excerpt evidence
= better completion, efficiency, and demonstrable policy grounding
```

The frozen cases and V2 reports are unchanged. The stricter evaluator can
regrade the stored V2 results over the diagnostic cohort without another model
run:

```bash
python -m evals.commit10.regrade
```

This writes:

```text
evals/commit10/reports/v2_cohort_regraded_report.json
```

The regraded V2 cohort has 0% task completion by construction: its 10
non-policy cases are the known V2 failures, and its 15 policy cases all fail the
new exact-citation-evidence requirement. This is a diagnostic baseline, not a
replacement for the preserved 80% completion result over all 50 V2 tasks.

Run V3 only on the same 25 cases: the 10 V2 completion/evidence failures plus
all 15 policy tasks.

```bash
python -m evals.commit10.runner \
  --case-id-file evals/commit10/v3_cohort_case_ids.txt \
  --results evals/commit10/reports/v3_cohort_results.jsonl \
  --report evals/commit10/reports/v3_cohort_report.json
```

Keep `model=gpt-5.6-luna` and `reasoning=none`. Review this cohort for
regressions before deciding whether a second 50-task run is worth the API cost.

## V3 finding and V4 campaign hypothesis

V3 completed 20 of the 25 diagnostic tasks. It fixed all 10 original
completion/evidence failures and all 10 support-policy tasks, while preserving
100% tool selection, arguments, conclusions, summary completion, and scalar
grounding. All five campaign-readiness tasks still failed.

Each campaign answer used the 10-item evidence maximum. Channel details consumed
the slots needed for campaign and consent policy evidence. V4 changes only the
campaign evidence allocation:

```text
overall eligibility status
+ campaign policy ID and exact excerpt
+ consent policy ID and exact excerpt
+ at most two channel details
= both required policy families evidenced within the existing schema limit
```

The report now also includes a `policy_tasks` section. This prevents non-policy
tasks, which pass policy checks vacuously, from inflating the policy headline.

Run only the five campaign cases:

```bash
python -m evals.commit10.runner \
  --case-id-file evals/commit10/v4_campaign_case_ids.txt \
  --results evals/commit10/reports/v4_campaign_results.jsonl \
  --report evals/commit10/reports/v4_campaign_report.json
```

## Full V4 run

After all five V4 campaign tasks pass without regressions:

```bash
python -m evals.commit10.runner
```

Interrupted runs can continue without repeating completed cases:

```bash
python -m evals.commit10.runner --resume
```

The V4 defaults deliberately use new files so earlier baselines are never
overwritten:

```text
evals/commit10/reports/v4_full_results.jsonl
evals/commit10/reports/v4_full_report.json
```

## Current status

The deterministic implementation, frozen cases, evaluator, and repository test
suite are complete. V1, V2, and V3 results are preserved. The targeted V4
campaign run and final 50-task V4 run both passed every task-completion metric.

Final V4 result:

```text
API success                        = 100%
correct tools and arguments         = 100%
correct conclusions                 = 100%
required evidence                   = 100%
policy citation evidence            = 100%
policy-family coverage              = 100%
task completion                     = 100%
unnecessary-tools empty             = 98%
mean / p50 / p95 latency            = 6.0616 / 5.4742 / 9.2174 s
estimated cost                      = $0.236846 total
```

V4 is accepted for Commit 10. One purchase task repeated a successful metrics
call. Exact policy citation evidence proves provenance but not semantic
entailment, and the frozen suite is a development regression set rather than a
holdout. Those limitations are recorded in `LEARNING_LOG.md` and Blog 10.
