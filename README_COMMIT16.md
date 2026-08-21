# SignalDesk Commit 16 - Observability, Evals, and Cost

Commit 16 makes every API-driven investigation attempt inspectable:

```text
investigation request
  -> request correlation
  -> accepted LangGraph investigator
  -> durable run observation
  -> analyst-scoped API
  -> observability dashboard
  -> optional human PASS / FAIL evaluation
```

The goal is operational evidence. This commit does not change the accepted
prompt, model, retriever, tool policy, or agent workflow.

## Question

> When an investigation is slow, expensive, wrong, or unavailable, can an
> engineer identify which run failed and inspect the relevant model, retrieval,
> tool, token, cost, latency, answer, and error evidence?

Commit 15 made the workflow usable. Commit 16 makes its behavior measurable and
debuggable.

## Run contract

Every authenticated, schema-valid request that reaches the investigator records
one `RunObservation` with:

```text
request_id
investigation_id, when successful
user_id
customer_id and question
status and task_success
model, prompt_version, reasoning_effort
tool calls and tool outcomes
retrieval document IDs and scores
input, cached input, output, reasoning, and total tokens
estimated cost
latency
final structured answer
human evaluation result and note
errors
start and completion timestamps
```

The same `REQ-...` identifier appears in the successful investigation response,
the observation record, and the `x-signaldesk-request-id` HTTP response header.
Failed requests still receive the header and create an error observation.

Authentication, CSRF, or schema failures happen before an agent run exists and
are therefore not agent-run observations.

## Metric definitions

The dashboard computes analyst-scoped metrics from up to the latest 1,000 local
observations:

| Metric | Definition |
|---|---|
| p50 / p95 latency | Percentiles across all recorded investigation attempts |
| tokens / task | Total recorded tokens divided by all attempts |
| cost / task | Total recorded estimated cost divided by all attempts |
| tool failure rate | Failed tool calls divided by all tool calls |
| retrieval failure rate | Failed or zero-result knowledge searches divided by all knowledge searches |
| task success rate | `COMPLETED` answers divided by all attempts |
| evaluation pass rate | Human `PASS` labels divided by all human-labeled runs |

Tasks that do not call knowledge search are excluded from the retrieval-failure
denominator. Runtime success and human evaluation are separate: a request may
complete successfully and still receive a `FAIL` quality label.

## Failure visibility

The public API returns a generic error, while the owned observation records:

```text
failure stage
exception type
bounded error message
elapsed time
model and prompt configuration
```

Tool failures inside an otherwise successful run are also preserved in the run
error list and included in the tool-failure rate.

If the model provider raises before returning usage, the current SDK boundary
does not expose partial token or cost data. Such failures record zero tokens and
unknown cost. The dashboard does not invent an estimate. This means aggregate
token and cost metrics are lower bounds when provider failures occur.

## Persistence and access

Observations use local SQLite at:

```text
data/runtime/commit16/observability.sqlite3
```

Rows are immutable except for the human evaluation label and note. Reads and
evaluation updates are scoped to the signed user ID. A second reviewer receives
an empty summary and `404` for another reviewer's run.

This is learning-scale local telemetry. It is not a trace backend, log export,
retention policy, tenant-wide operations view, or distributed transaction.

## Dashboard

The `Observability` application view provides:

```text
task success
p50 and p95 latency
tokens and cost per task
tool and retrieval failure rates
recent run ledger
selected-run model and prompt
token breakdown
final answer
tool calls
retrieval documents and scores
errors
human PASS / FAIL evaluation
```

The dashboard is an operational projection over persisted observations. It does
not replace the offline curated eval suites from earlier commits.

## API surface added

```text
GET  /api/v1/observability/summary
GET  /api/v1/observability/runs
GET  /api/v1/observability/runs/{request_id}
POST /api/v1/observability/runs/{request_id}/evaluation
```

The evaluation endpoint requires the signed session and CSRF token.

## Install and run

```bash
python -m pip install -r requirements-commit16.txt
```

Terminal 1:

```bash
export OPENAI_API_KEY="..."
export SIGNALDESK_ACCESS_CODE="signaldesk-local"
export SIGNALDESK_SESSION_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
python run_api.py
```

Terminal 2:

```bash
cd web
export NEXT_PUBLIC_SIGNALDESK_API_URL="http://127.0.0.1:8001"
npm run dev
```

Open `http://127.0.0.1:3000`, run an investigation, and select
`Observability`. Restart the API after pulling this commit because the new
routes and SQLite store are initialized at process startup.

The accepted model contract remains:

```text
model             gpt-5.6-luna
reasoning effort  none
prompt             commit10_v4_campaign_evidence_budget
```

## Verification

```bash
python -m pytest -q
python -m ruff check src/api src/observability tests/commit16

cd web
npm run typecheck
npm run lint
npm run build
```

Measured deterministic result:

```text
Commit 16 focused tests          7 passed
full repository tests           134 passed
OpenAPI paths                    12
Commit 16 Python lint            passed
frontend type-check             passed
frontend lint                   passed
frontend production build       passed
desktop dashboard workflow      passed
390px mobile dashboard          passed
external model calls            0
```

The browser check generated a frozen successful investigation through the real
HTTP boundary, verified its dashboard projection, applied a human `PASS` label,
and confirmed the aggregate evaluated count. The isolated test servers and
runtime directory were not used as model-quality evidence.

## Scope boundary

Commit 17 owns production hardening: structured log shipping, external trace
export, rate limits, managed secrets, deployment, load tests, dependency
failure injection, and reliability policies.

## What this milestone teaches

1. HTTP uptime does not explain an agent run.
2. Correlation IDs must cross API, persistence, and UI boundaries.
3. Metric names are meaningless without explicit denominators.
4. Runtime completion and answer quality are different measurements.
5. Retrieval and tool outcomes must remain queryable, not buried in logs.
6. Unknown token or cost data should stay unknown.
7. Observability must capture failures, not only successful answers.
