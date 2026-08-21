# SignalDesk Commit 17 - Production Hardening

Commit 17 asks a different question from the model and retrieval milestones:

> What happens when a dependency, request, or capacity assumption fails?

The system remains local, synthetic, and educational. Production hardening here
means making failure behavior explicit and testable. It does not mean claiming
that one Docker Compose file is a complete production platform.

The accepted AI behavior remains frozen:

```text
model             gpt-5.6-luna
reasoning effort  none
prompt             commit10_v4_campaign_evidence_budget
```

No prompt, retrieval-ranking, or agent-reasoning experiment is part of this
commit.

## Reliability contracts

### Liveness and readiness

```text
GET /api/v1/health        process liveness
GET /api/v1/health/ready  serving dependency readiness
```

Liveness stays `200` when the process can answer HTTP. Readiness returns `503`
when any required dependency is unavailable:

```text
customer warehouse
tool warehouse connection
approved knowledge corpus
investigation SQLite store
observability SQLite store
idempotency SQLite store
action SQLite store
```

This distinction prevents an orchestrator from routing new work to a process
that is alive but cannot serve trusted answers.

### Bounded model behavior

The existing agent already bounded each model request, retry count, model
rounds, and tool calls. Commit 17 makes those limits environment-configurable:

```text
SIGNALDESK_LLM_TIMEOUT_SECONDS
SIGNALDESK_LLM_MAX_ATTEMPTS
SIGNALDESK_MAX_MODEL_ROUNDS
SIGNALDESK_MAX_TOOL_CALLS
```

Only known transient provider errors are retried. Validation, policy, tool, and
agent-limit failures are not blindly retried. The timeout is a provider-request
timeout; Python cannot safely kill arbitrary work already executing in another
thread.

### Rate limiting

Login attempts are limited by client address. Investigations are limited by
signed user ID. A rejected request receives `429` and `Retry-After` before an
agent run is started.

The limiter is an in-memory sliding window. It is correct for this one-process
learning deployment, not a distributed multi-instance quota system.

### Idempotent investigations

Clients may send:

```http
Idempotency-Key: investigation-0001
```

The key is scoped to the signed user and canonical request payload.

```text
new key                   reserve and execute
same key + same payload   replay the persisted investigation
same key + other payload  409 conflict
active duplicate          409 in progress
stale/failed reservation  permit controlled retry
```

A replay performs no second model call and creates no second observability run.
The response includes `x-signaldesk-idempotent-replay: true` and the original
request ID.

SQLite makes this durable for one instance. A distributed deployment would use
a shared transactional store and a deliberate cross-store consistency design.

### Structured request logs

SignalDesk emits one JSON request event with:

```text
timestamp, level, event, request_id, method, path, status_code, duration_ms
```

Unexpected failures include only the exception type, not request bodies,
credentials, or raw provider messages. Model failures remain correlated with
the Commit 16 run observation.

### Secrets

Credentials still have no source-code defaults. They may be supplied directly
or through mounted secret files:

```text
SIGNALDESK_ACCESS_CODE or SIGNALDESK_ACCESS_CODE_FILE
SIGNALDESK_SESSION_SECRET or SIGNALDESK_SESSION_SECRET_FILE
```

Setting both forms is rejected. Secret values remain excluded from config
representations.

## Failure injection

The frozen matrix is in `evals/commit17/failure_matrix.json`.

```text
actual retrieval dependency unavailable  readiness 503, liveness 200
LLM timeout                              504 + sanitized observation
malformed tool output                    structured VALIDATION_ERROR
duplicate request                        persisted replay, one agent call
invalid customer                         bounded 404
retrieval returns zero documents         explicit zero-result envelope
agent loop                               configured-limit 503
capacity exceeded                        429 + Retry-After
```

The serving product uses the accepted lexical retriever. The roadmap's "vector
DB unavailable" case is therefore tested against the actual approved-knowledge
dependency instead of pretending the unused Commit 06 vector store is on the
runtime path.

Measured result:

```text
scenarios       8
passed          8
external calls  0
```

## Containers

`Dockerfile.api` builds a non-root Python 3.13 API image. `web/Dockerfile`
builds a non-root Node 22 standalone Next.js image. The warehouse is mounted
read-only, runtime SQLite data uses a named volume, and the API filesystem is
read-only except for that volume and `/tmp`.

Measured local image properties:

```text
API user   signaldesk
API size   337,556,935 bytes
Web user   node
Web size   224,581,918 bytes
```

Docker Compose requires the synthetic warehouse to exist under
`data/warehouse`. It does not silently generate data at container startup.

## CI

`.github/workflows/ci.yml` defines three independent jobs:

```text
backend     rebuild deterministic synthetic data, lint, test, coverage gate
frontend    install, type-check, lint, production build
containers  build API and web images
```

The backend gate requires at least 80% statement coverage over `src/api`. The
measured result is 92%. The first GitHub-hosted run exposed two environment
assumptions hidden by the developer machine: DuckDB required `pytz` for
timezone-aware results, and Customer 360 date calculations inherited the host
timezone. Commit 17 now declares `pytz` as a runtime dependency and configures
an explicit semantic timezone for warehouse builds and readers.

The corrected GitHub-hosted run passed backend, frontend, and container jobs:
<https://github.com/anilkulkarni87/SignalDesk/actions/runs/32453609629>.
This is useful clean-environment evidence, not evidence of real production
traffic or customer outcomes.

## Install and run locally

Runtime dependencies:

```bash
python -m pip install -r requirements-commit17.txt
```

Development and CI dependencies:

```bash
python -m pip install -r requirements-commit17-dev.txt
```

Run the API:

```bash
export OPENAI_API_KEY="..."
export SIGNALDESK_ACCESS_CODE="signaldesk-local"
export SIGNALDESK_SESSION_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
python run_api.py
```

Run the UI in another terminal:

```bash
cd web
export NEXT_PUBLIC_SIGNALDESK_API_URL="http://127.0.0.1:8001"
npm run dev
```

## Run with Docker Compose

```bash
cp .env.commit17.example .env.commit17
# Replace both placeholder values in .env.commit17.
docker compose --env-file .env.commit17 up --build
```

Open `http://127.0.0.1:3000`.

## Verification commands

```bash
python -m ruff check src tests evals run_api.py
python -m coverage run --source=src/api -m pytest -q
python -m coverage report --fail-under=80

cd web
npm run typecheck
npm run lint
npm run build
npm audit --omit=dev
```

Load smoke against a running API:

```bash
python evals/commit17/load_smoke.py \
  --base-url http://127.0.0.1:8001 \
  --requests 100 \
  --concurrency 10
```

Measured final result against the non-root API container:

```text
requests                         100
successful                       100
unhandled exceptions             0
p50                               8.847 ms
p95                              48.749 ms
throughput                       770.58 requests/second
```

This is a liveness-path smoke, not model-backed workflow capacity evidence.

## Final verification

```text
Commit 17 focused tests          14 passed
full repository tests           148 passed
OpenAPI paths                    13
API boundary coverage           92%
failure scenarios                8 / 8 passed
Python lint                      passed
frontend type-check              passed
frontend lint                    passed
frontend production build        passed
production npm vulnerabilities   0
Docker Compose configuration     valid
API image build/runtime          passed
web image build/runtime          passed
external model calls             0
```

The checked-in failure-injection report records the earlier 147-test snapshot.
It remains unchanged as an immutable experiment artifact; the additional test
guards the semantic timezone discovered by GitHub-hosted CI.

## What this milestone does not prove

- The health load smoke does not measure full investigation capacity.
- Deterministic failure injection is not a real provider outage drill.
- SQLite idempotency and in-memory rate limits are not distributed controls.
- Compose is not a managed deployment platform.
- There is no external log/trace backend, autoscaling policy, or pager system.
- The roadmap's 100 live agent scenarios were not rerun because hardening did
  not change agent behavior; existing deterministic agent tests remain in CI.

Commit 18 owns the FDE delivery pack: architecture, security, evaluation,
deployment, runbook, ROI, known limitations, roadmap, and a ten-minute demo.

## Learning conclusion

> Production hardening is not adding retries everywhere. It is deciding which
> failures are safe to retry, which work must be deduplicated, when an instance
> must stop receiving traffic, and how every failure remains observable.
