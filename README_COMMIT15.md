# SignalDesk Commit 15 - Production API and UI

Commit 15 turns the accepted SignalDesk workflows into a local analyst product:

```text
Next.js workspace
  -> authenticated FastAPI boundary
  -> existing Customer 360 and tool contracts
  -> accepted LangGraph investigator
  -> durable human approval workflow
```

The milestone is about product integration. It does not introduce a new prompt,
retriever, agent policy, or action-selection claim.

## Product workflow

An analyst can:

1. sign in to the local workspace;
2. search a warning-first customer queue;
3. inspect a PII-safe Customer 360 view;
4. ask the accepted investigation workflow a question;
5. inspect grounded evidence, policy sources, tool calls, and graph transitions;
6. draft a synthetic support follow-up; and
7. approve or reject its exact payload.

The support action is explicitly analyst-drafted. Commit 15 does not claim that
the agent learned to choose a real customer intervention.

## Architecture

```text
browser on localhost:3000
  -> signed HttpOnly session cookie + CSRF header
  -> FastAPI on localhost:8001
      -> read-only DuckDB customer data
      -> Commit 09 ToolRegistry
      -> Commit 10 accepted prompt
      -> Commit 11 LangGraph workflow
      -> Commit 12 durable approval workflow
      -> minimal SQLite product state
```

The API translates rich internal run objects into frontend-specific response
models. The browser receives useful summaries and provenance, not raw model
responses, database connections, secrets, or unrestricted tool access.

## Authentication boundary

This learning application uses a local access code and a signed session:

- the access code and signing secret come from environment variables;
- the session is stored in an `HttpOnly`, `SameSite=Strict` cookie;
- mutating requests require a per-session CSRF token;
- CORS allows only configured frontend origins;
- investigations and actions are scoped to the signed user ID.

This teaches the browser/API trust boundary. It is not enterprise identity. A
deployed customer system would use managed SSO, server-side authorization,
tenant policy, secret management, TLS, and session revocation.

## Install

Use the SignalDesk Python environment:

```bash
python -m pip install -r requirements-commit15.txt
```

Install the frontend dependencies once:

```bash
cd web
npm install
cd ..
```

Use Node.js `20.19+`, `22.13+`, or `24+`; Node 24 is the simplest current
choice. Node 23 is not in the supported range of the pinned lint toolchain.

## Run

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

Open `http://127.0.0.1:3000` and sign in with the reviewer ID of your choice and
the value of `SIGNALDESK_ACCESS_CODE`.

Use the same hostname on both sides. The strict cookie intentionally does not
support mixing `localhost` and `127.0.0.1`.

The accepted model contract remains:

```text
model             gpt-5.6-luna
reasoning effort  none
prompt             commit10_v4_campaign_evidence_budget
```

## API surface

```text
GET    /api/v1/health
POST   /api/v1/auth/session
GET    /api/v1/auth/session
DELETE /api/v1/auth/session
GET    /api/v1/customers
GET    /api/v1/customers/{customer_id}
POST   /api/v1/investigations
GET    /api/v1/investigations/{investigation_id}
POST   /api/v1/investigations/{investigation_id}/support-action
POST   /api/v1/actions/{action_id}/decision
```

FastAPI publishes the generated OpenAPI document at
`http://127.0.0.1:8001/docs` while the service is running.

## Verification

```bash
python -m pytest -q
python -m ruff check src/api src/actions/schemas.py tests/commit15 run_api.py

cd web
npm run typecheck
npm run lint
npm run build
```

Current deterministic backend result:

```text
Commit 15 API tests             18 passed
full repository tests          127 passed
Python lint                     passed
OpenAPI paths                   8
frontend type-check            passed
frontend lint                  passed
frontend production build      passed
desktop browser workflow       passed
390px mobile layout            passed
live model workflow timing     not measured yet
```

The browser verification used the real FastAPI process for authentication,
customer search, Customer 360, and failure handling. A deterministic frozen
investigator then exercised the answer, evidence, sources, tools, timeline, and
durable approval views without making an external model call. The exact action
was approved once and reached `EXECUTED`. The test server was stopped after the
check.

## Measure the roadmap outcome

The roadmap metric is a human workflow metric, not model latency:

```text
baseline  20-30 minutes per investigation
target    less than 3 minutes
```

For at least ten representative customers, start a timer when the analyst opens
the customer and stop when they have reviewed the answer and recorded an
approval decision. Report median, p95, and the percentage completed under three
minutes. Also preserve API latency separately.

Do not mark the target achieved from backend test latency or an agent report.
The real UI journey must be timed.

## Deliberate limits

Commit 16 owns comprehensive run observability, evaluation joins, cost
dashboards, and error telemetry. Commit 17 owns deployment, queues, rate limits,
managed identity, production databases, and reliability work.

Commit 15 therefore keeps only the product state needed to reload an
investigation and tie an approval to its owner. Runtime files remain under
`data/runtime/commit15` and are excluded from Git.

## What this milestone teaches

1. A working model call is not yet a usable product workflow.
2. Frontend response models should be explicit product contracts.
3. Authentication, CSRF, CORS, and ownership checks belong at the API boundary.
4. Existing deterministic tools should be reused rather than reimplemented for
   the UI.
5. Sources, tools, and workflow transitions make an agent result reviewable.
6. Human approval must show the exact payload that will execute.
7. Human task time and backend response time are different metrics.
