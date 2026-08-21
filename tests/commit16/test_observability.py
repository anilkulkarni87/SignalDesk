from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from src.api import APIConfig, SignalDeskService, create_app
from src.observability import (
    ObservedTokenUsage,
    ObservedToolCall,
    RunObservation,
    summarize,
)
from tests.commit15.test_api import (
    ACCESS_CODE,
    CUSTOMER_ID,
    SESSION_SECRET,
    FrozenInvestigator,
)


QUESTION = "Investigate current customer warning signals and supporting evidence."


class FailingInvestigator:
    def investigate(self, _customer_id: str, _question: str):
        raise RuntimeError("simulated provider outage")


def observation(
    request_id: str,
    *,
    latency: float,
    task_success: bool = True,
    tool_calls: list[ObservedToolCall] | None = None,
    evaluation: str = "NOT_EVALUATED",
) -> RunObservation:
    return RunObservation(
        request_id=request_id,
        investigation_id=f"INV-{request_id[-20:]}",
        user_id="USR-0123456789abcdef",
        customer_id=CUSTOMER_ID,
        question=QUESTION,
        status="SUCCESS",
        task_success=task_success,
        model="gpt-5.6-luna",
        prompt_version="commit10_v4_campaign_evidence_budget",
        reasoning_effort="none",
        tool_calls=tool_calls or [],
        retrieval_documents=[],
        retrieval_scores=[],
        tokens=ObservedTokenUsage(
            input=100,
            cached_input=10,
            output=20,
            reasoning=0,
            total=120,
        ),
        cost_usd=0.01,
        latency_seconds=latency,
        final_answer={"task_status": "COMPLETED"},
        evaluation_result=evaluation,
        evaluation_note="Reviewed result." if evaluation != "NOT_EVALUATED" else None,
        errors=[],
        started_at="2026-08-20T10:00:00+00:00",
        completed_at="2026-08-20T10:00:01+00:00",
    )


class Commit16ObservabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config = APIConfig(
            access_code=ACCESS_CODE,
            session_secret=SESSION_SECRET,
            runtime_dir=Path(self.temp_dir.name),
        )
        self.service = SignalDeskService(
            self.config,
            investigator_factory=lambda _registry: FrozenInvestigator(),
        )
        self.client_context = TestClient(create_app(self.config, service=self.service))
        self.client = self.client_context.__enter__()
        self.csrf = self._login(self.client, "observability-reviewer")

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
        return response.json()["csrf_token"]

    def _investigate(self, client: TestClient | None = None, csrf: str | None = None):
        return (client or self.client).post(
            "/api/v1/investigations",
            headers={"x-signaldesk-csrf": csrf or self.csrf},
            json={"customer_id": CUSTOMER_ID, "question": QUESTION},
        )

    def test_request_id_correlates_response_header_answer_and_run_record(self):
        response = self._investigate()

        self.assertEqual(response.status_code, 201, response.text)
        request_id = response.json()["request_id"]
        self.assertEqual(response.headers["x-signaldesk-request-id"], request_id)
        detail = self.client.get(f"/api/v1/observability/runs/{request_id}")
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["request_id"], request_id)

    def test_success_record_contains_required_model_tool_retrieval_and_cost_fields(
        self,
    ):
        created = self._investigate().json()
        run = self.client.get(
            f"/api/v1/observability/runs/{created['request_id']}"
        ).json()

        self.assertEqual(run["status"], "SUCCESS")
        self.assertTrue(run["task_success"])
        self.assertEqual(run["model"], "gpt-5.6-luna")
        self.assertEqual(run["reasoning_effort"], "none")
        self.assertEqual(len(run["tool_calls"]), 2)
        self.assertEqual(run["retrieval_documents"], ["KB-00108"])
        self.assertEqual(run["retrieval_scores"], [0.91])
        self.assertEqual(run["tokens"]["total"], 1440)
        self.assertEqual(run["cost_usd"], 0.0042)
        self.assertGreater(run["latency_seconds"], 0)
        self.assertEqual(run["final_answer"]["task_status"], "COMPLETED")
        self.assertEqual(run["evaluation_result"], "NOT_EVALUATED")
        self.assertEqual(run["errors"], [])

    def test_summary_reports_roadmap_metrics(self):
        self._investigate()
        summary = self.client.get("/api/v1/observability/summary").json()

        self.assertEqual(summary["total_runs"], 1)
        self.assertEqual(summary["task_success_rate_pct"], 100)
        self.assertEqual(summary["tokens_per_task"], 1440)
        self.assertEqual(summary["cost_per_task_usd"], 0.0042)
        self.assertEqual(summary["tool_failure_rate_pct"], 0)
        self.assertEqual(summary["retrieval_failure_rate_pct"], 0)
        self.assertEqual(summary["latency_seconds"]["p50"], 1.25)
        self.assertEqual(summary["latency_seconds"]["p95"], 1.25)

    def test_failed_agent_attempt_is_recorded_with_sanitized_api_response(self):
        failing_service = SignalDeskService(
            self.config,
            investigator_factory=lambda _registry: FailingInvestigator(),
        )
        failing_context = TestClient(create_app(self.config, service=failing_service))
        failing_client = failing_context.__enter__()
        try:
            csrf = self._login(failing_client, "failure-reviewer")
            response = self._investigate(failing_client, csrf)
            runs = failing_client.get("/api/v1/observability/runs").json()["runs"]
        finally:
            failing_context.__exit__(None, None, None)
            failing_service.close()

        self.assertEqual(response.status_code, 503)
        self.assertNotIn("simulated provider outage", response.text)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["status"], "ERROR")
        self.assertFalse(runs[0]["task_success"])
        self.assertEqual(runs[0]["errors"][0]["stage"], "agent_investigation")
        self.assertEqual(runs[0]["errors"][0]["error_type"], "RuntimeError")

    def test_runs_are_visible_only_to_the_signed_user(self):
        created = self._investigate().json()
        other = TestClient(create_app(self.config, service=self.service))
        csrf = self._login(other, "other-observability-reviewer")

        detail = other.get(f"/api/v1/observability/runs/{created['request_id']}")
        summary = other.get("/api/v1/observability/summary")
        missing_csrf = other.post(
            f"/api/v1/observability/runs/{created['request_id']}/evaluation",
            json={"result": "PASS", "note": "This should not be accepted."},
        )

        self.assertGreaterEqual(len(csrf), 32)
        self.assertEqual(detail.status_code, 404)
        self.assertEqual(summary.json()["total_runs"], 0)
        self.assertEqual(missing_csrf.status_code, 403)

    def test_human_evaluation_updates_the_owned_run(self):
        created = self._investigate().json()
        response = self.client.post(
            f"/api/v1/observability/runs/{created['request_id']}/evaluation",
            headers={"x-signaldesk-csrf": self.csrf},
            json={
                "result": "PASS",
                "note": "Evidence and conclusion were reviewed together.",
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["evaluation_result"], "PASS")
        summary = self.client.get("/api/v1/observability/summary").json()
        self.assertEqual(summary["evaluated_runs"], 1)
        self.assertEqual(summary["evaluation_pass_rate_pct"], 100)

    def test_metric_denominators_include_failed_tools_and_zero_result_retrieval(self):
        runs = [
            observation(
                "REQ-00000000000000000001",
                latency=1,
                evaluation="PASS",
                tool_calls=[
                    ObservedToolCall(
                        round_number=1,
                        tool_name="search_knowledge_base",
                        success=True,
                        error_code=None,
                        latency_ms=10,
                        returned_count=0,
                    )
                ],
            ),
            observation(
                "REQ-00000000000000000002",
                latency=3,
                task_success=False,
                evaluation="FAIL",
                tool_calls=[
                    ObservedToolCall(
                        round_number=1,
                        tool_name="search_knowledge_base",
                        success=False,
                        error_code="INTERNAL_ERROR",
                        latency_ms=20,
                        returned_count=None,
                    ),
                    ObservedToolCall(
                        round_number=1,
                        tool_name="get_customer_profile",
                        success=True,
                        error_code=None,
                        latency_ms=5,
                    ),
                ],
            ),
        ]

        summary = summarize(runs)

        self.assertEqual(summary.task_success_rate_pct, 50)
        self.assertEqual(summary.latency_seconds.p50, 2)
        self.assertEqual(summary.latency_seconds.p95, 2.9)
        self.assertEqual(summary.tool_failure_rate_pct, 33.33)
        self.assertEqual(summary.retrieval_failure_rate_pct, 100)
        self.assertEqual(summary.evaluation_pass_rate_pct, 50)


if __name__ == "__main__":
    unittest.main()
