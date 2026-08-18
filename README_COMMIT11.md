# SignalDesk Commit 11 - Stateful Investigation With LangGraph

Commit 11 replaces the implicit control flow in the accepted Commit 10 agent
loop with an explicit, checkpointed state graph. It does not change the model,
prompt, tools, customer cases, answer schema, or evaluator.

The experiment asks one narrow question:

> What does explicit workflow orchestration add when model behavior is held
> constant?

## Fixed treatment boundary

```text
fixed                              changed
-----                              -------
gpt-5.6-luna                       orchestration runtime
reasoning = none                   explicit typed state
Commit 10 V4 prompt                named nodes and routes
six read-only tools                in-memory checkpoints
50 frozen customers                resume after node failure
InvestigationAnswer schema         transition observability
Commit 10 V4 evaluator
```

The Commit 10 `CustomerInvestigator` remains unchanged as the baseline.
`LangGraphCustomerInvestigator` subclasses its deterministic runtime boundaries
and changes only how control moves between model and tools.

## Explicit graph

```text
START
  -> interpret_request
  -> resolve_customer
  -> investigation_router
       -> profile -----------+
       -> events ------------+-> investigation_router
       -> knowledge ---------+
       -> reason_about_case -+
       -> recommend_action
  -> approval_required
       -> finish
       -> execute_action (guarded and unreachable in Commit 11)
  -> END
```

The router sends each model-requested tool to one of three data nodes:

```text
profile   profile, metrics, campaign eligibility
events    customer events, purchase history
knowledge approved knowledge search
```

Tool calls are still validated by the Commit 09 registry and bound to the task
customer. The graph does not receive SQL access.

## State and checkpoints

Graph state carries:

```text
validated request and resolved customer
Responses API input transcript
pending function calls
typed tool traces
token and request totals
final structured answer
current route and transition history
safety-gate status
```

An `InMemorySaver` writes a checkpoint after every graph step. If a node fails,
`resume(thread_id)` continues from the last successful checkpoint. In-memory
persistence is appropriate for this learning experiment; it is not durable
across process restarts and is not a production state store.

## Action boundary

The roadmap diagram includes recommendation, approval, and execution nodes.
Commit 12 owns real human approval and actions, so Commit 11 terminates with:

```text
recommendation    = ANALYSIS_ONLY
approval_required = false
action_executed   = false
```

The `execute_action` node raises a safety error if reached. This makes the
future boundary visible without introducing write authority early.

## Two evaluations, two claims

### 1. Deterministic 100-scenario replay

The 50 accepted Commit 10 runs are replayed in two modes:

```text
standard               normal graph execution
checkpoint_recovery    fail reason_about_case once, then resume
```

This benchmark tests graph wiring, routing, tool counts, checkpoint recovery,
and the action boundary without making model API calls. It does not measure a
new prompt or estimate model accuracy.

Current result:

```text
scenarios                  100
completion                 100%
correct routing            100%
tool-count agreement       100%
rubric task completion     100%
recovery                   100%
average tool calls         2.22
failed executions          0
actions executed           0
```

### 2. Live 50-case comparison

The live runner executes the same frozen cases through LangGraph. The comparison
then measures regressions, answer metrics, latency, tool calls, tokens, and cost
against the stored Commit 10 V4 baseline. This is the experiment that can show
whether orchestration preserved model behavior in one new stochastic run.

## Install and verify

```bash
python -m pip install -r requirements-commit11.txt
python -m unittest discover -s tests -v
python -m evals.commit11.make_scenarios
python -m evals.commit11.replay_benchmark
```

## Run a live pilot

Make `OPENAI_API_KEY` available in the same terminal, then run one frozen case
from each of the six task categories:

```bash
python -m evals.commit11.runner \
  --case-id-file evals/commit11/cross_category_case_ids.txt \
  --results evals/commit11/reports/langgraph_cross_category_results.jsonl \
  --report evals/commit11/reports/langgraph_cross_category_report.json
```

Review transitions and tool traces before running all 50:

```bash
python -m evals.commit11.runner
python -m evals.commit11.compare
```

Use `--resume` with the live runner to skip cases already written after a
process interruption. This is runner-level continuation; graph-level
checkpoint resume is separately tested in the deterministic benchmark.

## What this milestone teaches

1. A loop and a graph can implement the same external behavior.
2. Explicit state makes routing, stopping, and safety decisions inspectable.
3. Checkpoints turn a failed node into a resumable workflow boundary.
4. Framework adoption is not prompt improvement and needs a controlled
   comparison.
5. Persistence mechanics do not replace tool validation, grounding, or evals.
6. Human approval and write-capable actions should arrive only after the
   read-only state machine is measured.
