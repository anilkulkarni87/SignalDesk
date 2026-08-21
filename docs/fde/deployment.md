# Local Deployment Guide

## Learning scope

This guide runs SignalDesk on one development machine with synthetic data. It is not a production deployment design and does not include managed identity, high availability, regional controls, or operational support.

## Components

| Component | Default address | Purpose |
|---|---|---|
| FastAPI service | `http://127.0.0.1:8001` | Authentication, tools, investigation, actions, and observability APIs |
| API documentation | `http://127.0.0.1:8001/docs` | Interactive API contract |
| Next.js application | `http://127.0.0.1:3000` | Analyst workspace and observability UI |
| Local data | Repository `data/` and local runtime files | Synthetic warehouse, knowledge, indexes, audit, and checkpoints |

The API intentionally has no `GET /` page. A 404 at port 8001 root is expected; use `/docs` or the frontend at port 3000.

## Prerequisites

- Python version supported by the repository and a dedicated virtual environment.
- Node.js and npm for `web/`.
- An OpenAI API key for live investigation calls.
- Generated synthetic data and knowledge artifacts.
- Ports 8001 and 3000 available.

## Install

From the repository root:

```bash
python -m pip install -r requirements-commit17.txt
cd web
npm ci
cd ..
```

For repository tests and linting, install the development dependencies too:

```bash
python -m pip install -r requirements-commit17-dev.txt
```

Use the repository's dedicated environment. A previously observed Agents SDK type error came from mixing a project environment with Anaconda's standard library; environment isolation is part of the exercise.

## Configure

Set local-only values in each terminal that needs them:

```bash
export OPENAI_API_KEY="your-local-key"
export SIGNALDESK_ACCESS_CODE="signaldesk-local"
export SIGNALDESK_SESSION_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
```

Do not commit these values. The access code is intentionally simple because this is a local learning environment.

## Start the API

```bash
python run_api.py
```

Confirm:

```bash
curl http://127.0.0.1:8001/api/v1/health
curl http://127.0.0.1:8001/api/v1/health/ready
```

## Start the web application

In a second terminal:

```bash
cd web
npm run dev
```

Open `http://127.0.0.1:3000`. Use one hostname consistently. If the browser uses `127.0.0.1`, the frontend development server must allow that origin as configured in `web/next.config.ts`.

## Optional container path

```bash
cp .env.commit17.example .env.commit17
# Replace both placeholder values in .env.commit17.
docker compose --env-file .env.commit17 up --build
```

The compose path is a packaging and startup exercise, not evidence of a resilient multi-service deployment.

## Verification

```bash
python -m pytest -q
python -m pytest tests/commit17 -q
python evals/commit17/load_smoke.py \
  --base-url http://127.0.0.1:8001 \
  --requests 100 \
  --concurrency 10
```

The failure suite uses injected local dependencies. The liveness smoke measures a lightweight health endpoint, not model throughput or end-to-end capacity.

## Production gaps

A real deployment would still require managed identity, a secrets manager, encrypted managed stores, backups, schema migrations, ingress policy, rate limits, network controls, centralized telemetry, alerting, horizontal capacity tests, disaster recovery, and a supported release process.
