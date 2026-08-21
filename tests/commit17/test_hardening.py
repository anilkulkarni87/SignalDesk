from __future__ import annotations

import json
import logging
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from evals.commit17.load_smoke import summarize
from src.agent.investigator import AgentLimitError
from src.api import APIConfig, SignalDeskService, create_app
from src.api.logging import JsonLogFormatter
from src.api.resilience import IdempotencyInProgress, IdempotencyStore
from src.llm.retry import with_exponential_backoff
from src.warehouse import SEMANTIC_TIMEZONE, configure_semantic_timezone
from tests.commit15.test_api import (
    ACCESS_CODE,
    CUSTOMER_ID,
    SESSION_SECRET,
    FrozenInvestigator,
)


QUESTION = "Investigate current customer warning signals and supporting evidence."


class CountingInvestigator(FrozenInvestigator):
    def __init__(self) -> None:
        self.calls = 0

    def investigate(self, customer_id: str, question: str):
        self.calls += 1
        return super().investigate(customer_id, question)


class TimeoutInvestigator:
    def investigate(self, _customer_id: str, _question: str):
        raise TimeoutError("provider detail that must not reach the analyst")


class LoopingInvestigator:
    def investigate(self, _customer_id: str, _question: str):
        raise AgentLimitError("agent exceeded max_model_rounds")


class TransientFailure(RuntimeError):
    pass


class Commit17HardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config = APIConfig(
            access_code=ACCESS_CODE,
            session_secret=SESSION_SECRET,
            runtime_dir=Path(self.temp_dir.name),
            login_rate_limit=100,
            investigation_rate_limit=100,
        )
        self.investigator = CountingInvestigator()
        self.service = SignalDeskService(
            self.config,
            investigator_factory=lambda _registry: self.investigator,
        )
        self.client_context = TestClient(create_app(self.config, service=self.service))
        self.client = self.client_context.__enter__()
        self.csrf = self._login(self.client, "hardening-reviewer")

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        self.service.close()
        self.temp_dir.cleanup()

    @staticmethod
    def _login(client: TestClient, reviewer_id: str) -> str:
        response = client.post(
            "/api/v1/auth/session",
            json={"access_code": ACCESS_CODE, "reviewer_id": reviewer_id},
        )
        if response.status_code != 200:
            raise AssertionError(response.text)
        return response.json()["csrf_token"]

    def _investigate(
        self,
        *,
        key: str | None = None,
        question: str = QUESTION,
        client: TestClient | None = None,
        csrf: str | None = None,
    ):
        headers = {"x-signaldesk-csrf": csrf or self.csrf}
        if key:
            headers["Idempotency-Key"] = key
        return (client or self.client).post(
            "/api/v1/investigations",
            headers=headers,
            json={"customer_id": CUSTOMER_ID, "question": question},
        )

    def test_duckdb_connections_use_explicit_semantic_timezone(self):
        import duckdb

        connection = duckdb.connect()
        try:
            connection.execute("SET TimeZone = 'UTC'")
            configure_semantic_timezone(connection)
            configured = connection.execute(
                "SELECT current_setting('TimeZone')"
            ).fetchone()[0]
        finally:
            connection.close()

        self.assertEqual(configured, SEMANTIC_TIMEZONE)

    def test_liveness_stays_up_while_readiness_reports_dependency_failure(self):
        ready = self.client.get("/api/v1/health/ready")
        original = self.service._cdp_tools.readiness
        self.service._cdp_tools.readiness = lambda: {
            "tool_warehouse": True,
            "approved_knowledge": False,
        }
        try:
            degraded = self.client.get("/api/v1/health/ready")
            live = self.client.get("/api/v1/health")
        finally:
            self.service._cdp_tools.readiness = original

        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.json()["status"], "ready")
        self.assertEqual(degraded.status_code, 503)
        self.assertEqual(
            degraded.json()["checks"]["approved_knowledge"],
            "unavailable",
        )
        self.assertEqual(live.status_code, 200)

    def test_duplicate_request_replays_without_second_agent_run(self):
        first = self._investigate(key="investigation-0001")
        replay = self._investigate(key="investigation-0001")

        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(self.investigator.calls, 1)
        self.assertEqual(
            replay.json()["investigation_id"],
            first.json()["investigation_id"],
        )
        self.assertEqual(replay.headers["x-signaldesk-idempotent-replay"], "true")
        self.assertEqual(
            replay.headers["x-signaldesk-original-request-id"],
            first.json()["request_id"],
        )
        summary = self.client.get("/api/v1/observability/summary").json()
        self.assertEqual(summary["total_runs"], 1)

    def test_reused_idempotency_key_with_different_input_conflicts(self):
        first = self._investigate(key="investigation-0002")
        conflict = self._investigate(
            key="investigation-0002",
            question="Investigate this customer's current support warning evidence.",
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(self.investigator.calls, 1)

    def test_investigation_rate_limit_returns_retry_after(self):
        limited_config = APIConfig(
            access_code=ACCESS_CODE,
            session_secret=SESSION_SECRET,
            runtime_dir=Path(self.temp_dir.name) / "rate-limit",
            login_rate_limit=100,
            investigation_rate_limit=2,
        )
        investigator = CountingInvestigator()
        service = SignalDeskService(
            limited_config,
            investigator_factory=lambda _registry: investigator,
        )
        context = TestClient(create_app(limited_config, service=service))
        client = context.__enter__()
        try:
            csrf = self._login(client, "rate-limit-reviewer")
            first = self._investigate(client=client, csrf=csrf)
            second = self._investigate(client=client, csrf=csrf)
            limited = self._investigate(client=client, csrf=csrf)
        finally:
            context.__exit__(None, None, None)
            service.close()

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(limited.status_code, 429)
        self.assertGreaterEqual(int(limited.headers["Retry-After"]), 1)
        self.assertEqual(investigator.calls, 2)

    def test_timeout_returns_504_and_records_sanitized_failure(self):
        response, run = self._failure_run(TimeoutInvestigator())

        self.assertEqual(response.status_code, 504)
        self.assertEqual(response.json()["detail"], "The model dependency timed out.")
        self.assertEqual(run["errors"][0]["error_type"], "TimeoutError")
        self.assertNotIn("provider detail", json.dumps(run))

    def test_agent_loop_limit_returns_bounded_failure(self):
        response, run = self._failure_run(LoopingInvestigator())

        self.assertEqual(response.status_code, 503)
        self.assertIn("configured safety limit", response.json()["detail"])
        self.assertEqual(run["errors"][0]["error_type"], "AgentLimitError")

    def _failure_run(self, investigator) -> tuple[object, dict]:
        runtime = Path(self.temp_dir.name) / investigator.__class__.__name__
        config = replace(self.config, runtime_dir=runtime)
        service = SignalDeskService(
            config,
            investigator_factory=lambda _registry: investigator,
        )
        context = TestClient(create_app(config, service=service))
        client = context.__enter__()
        try:
            csrf = self._login(client, f"{investigator.__class__.__name__}-reviewer")
            response = self._investigate(client=client, csrf=csrf)
            run = client.get("/api/v1/observability/runs").json()["runs"][0]
        finally:
            context.__exit__(None, None, None)
            service.close()
        return response, run

    def test_malformed_tool_output_becomes_structured_validation_failure(self):
        name = "get_customer_profile"
        original = self.service._registry._specs[name]
        self.service._registry._specs[name] = replace(
            original,
            handler=lambda _payload: {},
        )
        try:
            result = self.service._registry.execute(
                name,
                {"customer_id": CUSTOMER_ID},
            )
        finally:
            self.service._registry._specs[name] = original

        self.assertFalse(result.success)
        self.assertEqual(result.error.code, "VALIDATION_ERROR")
        self.assertIsNone(result.output)

    def test_zero_document_retrieval_is_explicit_success_not_exception(self):
        result = self.service._registry.execute(
            "search_knowledge_base",
            {"query": "zzzxxyyqqqterm", "top_k": 3},
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output["returned_count"], 0)
        self.assertEqual(result.output["results"], [])

    def test_stale_idempotency_reservation_can_be_recovered(self):
        now = [1000.0]
        path = Path(self.temp_dir.name) / "stale.sqlite3"
        store = IdempotencyStore(
            path,
            pending_ttl_seconds=30,
            clock=lambda: now[0],
        )
        try:
            first = store.begin("user", "stale-key", "hash", "request-1")
            with self.assertRaises(IdempotencyInProgress):
                store.begin("user", "stale-key", "hash", "request-2")
            now[0] += 31
            recovered = store.begin("user", "stale-key", "hash", "request-3")
        finally:
            store.close()

        self.assertEqual(first.action, "PROCEED")
        self.assertEqual(recovered.action, "PROCEED")

    def test_retry_policy_retries_only_declared_transient_error(self):
        attempts = 0

        def operation():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise TransientFailure("temporary")
            return "ok"

        result, attempts_used = with_exponential_backoff(
            operation,
            retryable_exceptions=(TransientFailure,),
            max_attempts=3,
            base_delay_seconds=0,
            max_delay_seconds=0,
        )

        self.assertEqual(result, "ok")
        self.assertEqual(attempts_used, 3)

    def test_secret_files_are_supported_without_secret_defaults(self):
        access_file = Path(self.temp_dir.name) / "access.txt"
        secret_file = Path(self.temp_dir.name) / "session.txt"
        access_file.write_text(ACCESS_CODE, encoding="utf-8")
        secret_file.write_text(SESSION_SECRET, encoding="utf-8")
        environment = {
            "SIGNALDESK_ACCESS_CODE_FILE": str(access_file),
            "SIGNALDESK_SESSION_SECRET_FILE": str(secret_file),
        }

        with patch.dict(os.environ, environment, clear=True):
            config = APIConfig.from_env()

        self.assertEqual(config.access_code, ACCESS_CODE)
        self.assertEqual(config.session_secret, SESSION_SECRET)
        self.assertNotIn(ACCESS_CODE, repr(config))
        self.assertNotIn(SESSION_SECRET, repr(config))

    def test_structured_log_formatter_emits_correlation_fields(self):
        record = logging.LogRecord(
            "signaldesk.test",
            logging.INFO,
            __file__,
            1,
            "http_request",
            (),
            None,
        )
        record.event = "http_request"
        record.request_id = "REQ-0123456789abcdefabcd"
        record.status_code = 200

        payload = json.loads(JsonLogFormatter().format(record))

        self.assertEqual(payload["event"], "http_request")
        self.assertEqual(payload["request_id"], record.request_id)
        self.assertEqual(payload["status_code"], 200)
        self.assertIn("timestamp", payload)

    def test_load_smoke_summary_uses_latency_distribution_and_error_rate(self):
        report = summarize(
            [
                {"status_code": 200, "latency_ms": 10, "exception": None},
                {"status_code": 200, "latency_ms": 20, "exception": None},
                {"status_code": 503, "latency_ms": 30, "exception": None},
                {"status_code": 0, "latency_ms": 40, "exception": "TimeoutError"},
            ],
            elapsed_seconds=0.5,
        )

        self.assertEqual(report["success_rate_pct"], 50)
        self.assertEqual(report["latency_ms"]["p50"], 25)
        self.assertEqual(report["latency_ms"]["p95"], 38.5)
        self.assertEqual(report["unhandled_exceptions"], 1)
        self.assertEqual(report["throughput_requests_per_second"], 8)


if __name__ == "__main__":
    unittest.main()
