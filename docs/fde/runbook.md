# Local Operations Runbook

## Learning scope

This runbook teaches operational thinking for the local synthetic system. It does not establish an on-call service, production SLO, or customer support commitment.

## Start-of-session checklist

1. Confirm the repository revision and working tree state.
2. Activate the repository's Python environment.
3. Set the model key, local access code, and a fresh session secret.
4. Start the API and verify both health endpoints.
5. Start the frontend and open port 3000.
6. Sign in, run one known synthetic investigation, and confirm it appears in observability.
7. Keep write demonstrations synthetic and approval-gated.

## Diagnosis order

When a request fails, inspect in this order:

1. Request ID and HTTP status.
2. Liveness and readiness.
3. Authentication/session state.
4. Tool failure details and argument bounds.
5. Retrieval document IDs and scores.
6. Model response, timeout, and schema validation.
7. Approval/audit state for actions.
8. Local dependency, file, or database availability.

This order narrows the failing boundary before changing prompts or retrying blindly.

## Common conditions

| Symptom | Meaning | Response |
|---|---|---|
| `GET /` returns 404 on port 8001 | Expected API behavior | Open `/docs` or port 3000 |
| Frontend chunks or HMR blocked for `127.0.0.1` | Development origin mismatch | Use one hostname and confirm `allowedDevOrigins` |
| 401 response | Missing or expired local session | Sign in again; confirm access-code environment |
| Readiness is 503 | Required local dependency is unavailable | Inspect readiness detail; restore the named dependency before retrying |
| Investigation timeout | Model or tool exceeded its boundary | Preserve request ID; inspect which stage timed out; retry only when safe |
| Tool argument rejection | Model/user supplied an out-of-contract value | Correct the bounded input; do not relax validation for one case |
| No policy result | Corpus/index missing, query mismatch, or current-approved filter | Verify generated knowledge and index; inspect retrieval trace |
| Duplicate action response | Existing idempotency key was reused | Inspect the original audit record; do not execute a second action |
| Action remains pending | No decision has been recorded | Resume the same workflow thread and review the exact payload |
| Missing `pytz` in CI | Runtime dependency omitted | Install from the corrected lock/requirements and rerun cleanly |
| Time-sensitive tests differ by machine | Host timezone leaked into fixtures | Use explicit UTC fixture reads and rerun the focused suite |

## Recovery boundaries

- Model failure: return a typed failure and preserve the request ID. Do not fabricate an answer.
- Retrieval failure: expose that grounding is unavailable. Do not allow uncited policy guidance.
- Customer tool failure: stop the investigation because customer evidence is incomplete.
- Approval-store interruption: resume by action/thread ID; idempotency must prevent duplicate execution.
- UI failure: use API documentation only for diagnosis, not as a bypass around authorization or approval.

## Local rollback

1. Stop the frontend and API processes.
2. Preserve relevant logs, reports, and request IDs.
3. Return to the last reviewed Git revision using normal branch operations.
4. Reinstall dependencies only if the revision changed them.
5. Run focused tests, then the full suite, before restarting the demo.

Do not delete checkpoints or audit records to make a failed workflow appear clean. Use a new synthetic action ID for a new scenario.

## Evidence to capture

For a learning incident, record:

- Revision, date, environment, and command.
- Customer and case IDs, excluding real PII.
- Request, workflow, and action IDs.
- Expected and actual boundary behavior.
- Tool, retrieval, model, and approval state.
- Whether retry was attempted and whether it was safe.
- The smallest regression test that reproduces the issue.

The [Commit 17 failure report](../../evals/commit17/reports/failure_injection_report.json) is the reference format for controlled failure evidence.

