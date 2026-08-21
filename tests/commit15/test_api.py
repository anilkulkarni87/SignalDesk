from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from src.agent.schemas import (
    AgentRunMetrics,
    InvestigationAnswer,
    InvestigationRequest,
    ToolTrace,
)
from src.api import APIConfig, SignalDeskService, create_app
from src.api.auth import InvalidSessionError, SessionManager
from src.workflow.schemas import WorkflowMetrics, WorkflowRun


ACCESS_CODE = "signaldesk-learning-access"
SESSION_SECRET = "commit15-test-session-secret-at-least-32-characters"
CUSTOMER_ID = "C0046145"


class FrozenInvestigator:
    def investigate(self, customer_id: str, question: str) -> WorkflowRun:
        return WorkflowRun(
            request=InvestigationRequest(
                customer_id=customer_id,
                question=question,
            ),
            answer=InvestigationAnswer(
                customer_id=customer_id,
                task_status="COMPLETED",
                conclusion_code="MULTIPLE_WARNING_SIGNALS",
                risk_level="HIGH",
                summary=(
                    "Purchase and engagement warning signals require analyst review."
                ),
                evidence=[
                    {
                        "source_tool": "calculate_customer_metrics",
                        "field": "purchase.purchase_decline_flag",
                        "value": True,
                        "interpretation": "The purchase warning flag is active.",
                    }
                ],
                policy_document_ids=["KB-00108"],
                limitations=[],
            ),
            tool_trace=[
                ToolTrace(
                    round_number=1,
                    call_id="call-metrics",
                    tool_name="calculate_customer_metrics",
                    arguments={"customer_id": customer_id},
                    success=True,
                    error_code=None,
                    latency_ms=4.2,
                    output={
                        "purchase": {"purchase_decline_flag": True},
                        "engagement": {"engagement_decline_flag": True},
                        "support": {"support_attention_flag": False},
                    },
                ),
                ToolTrace(
                    round_number=1,
                    call_id="call-knowledge",
                    tool_name="search_knowledge_base",
                    arguments={
                        "query": "retention investigation",
                        "families": ["retention"],
                        "top_k": 3,
                    },
                    success=True,
                    error_code=None,
                    latency_ms=2.1,
                    output={
                        "returned_count": 1,
                        "results": [
                            {
                                "document_id": "KB-00108",
                                "title": "Retention review policy",
                                "family": "retention",
                                "excerpt": "Analysts must review warning evidence.",
                                "score": 0.91,
                            }
                        ],
                    },
                ),
            ],
            metrics=AgentRunMetrics(
                model="gpt-5.6-luna",
                prompt_version="commit10_v4_campaign_evidence_budget",
                reasoning_effort="none",
                response_ids=["resp-frozen"],
                model_rounds=1,
                tool_calls=2,
                api_requests=1,
                api_attempts=1,
                api_retry_attempts=0,
                input_tokens=1200,
                cached_input_tokens=0,
                output_tokens=240,
                reasoning_tokens=0,
                total_tokens=1440,
                latency_seconds=1.25,
                estimated_cost_usd=0.0042,
            ),
            raw_output_text="{}",
            workflow=WorkflowMetrics(
                workflow_version="commit11_v1_explicit_stateful_investigation",
                thread_id="thread-frozen",
                transitions=[
                    "interpret_request",
                    "resolve_customer",
                    "investigation_router",
                    "profile",
                    "investigation_router",
                    "knowledge",
                    "investigation_router",
                    "reason_about_case",
                    "investigation_router",
                    "recommend_action",
                    "approval_required",
                    "finish",
                ],
                routed_tool_nodes=["profile", "knowledge"],
                checkpoint_count=12,
                resume_count=0,
                recommendation="ANALYSIS_ONLY",
                approval_required=False,
                action_executed=False,
            ),
        )


class Commit15APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.config = APIConfig(
            access_code=ACCESS_CODE,
            session_secret=SESSION_SECRET,
            runtime_dir=Path(cls.temp_dir.name),
        )
        cls.service = SignalDeskService(
            cls.config,
            investigator_factory=lambda _registry: FrozenInvestigator(),
        )
        cls.app = create_app(cls.config, service=cls.service)
        cls.client_context = TestClient(cls.app)
        cls.client = cls.client_context.__enter__()
        cls.csrf = cls._login(cls.client, "commit15-reviewer")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)
        cls.service.close()
        cls.temp_dir.cleanup()

    @staticmethod
    def _login(client: TestClient, reviewer_id: str) -> str:
        response = client.post(
            "/api/v1/auth/session",
            json={
                "access_code": ACCESS_CODE,
                "reviewer_id": reviewer_id,
            },
        )
        if response.status_code != 200:
            raise AssertionError(response.text)
        return response.json()["csrf_token"]

    def write_headers(self, csrf: str | None = None) -> dict[str, str]:
        return {"x-signaldesk-csrf": csrf or self.csrf}

    def create_investigation(self) -> dict:
        response = self.client.post(
            "/api/v1/investigations",
            headers=self.write_headers(),
            json={
                "customer_id": CUSTOMER_ID,
                "question": "Investigate current customer warning signals and evidence.",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_health_is_public(self):
        response = TestClient(self.app).get("/api/v1/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["version"], "commit15_v1")

    def test_protected_endpoint_requires_session(self):
        response = TestClient(self.app).get("/api/v1/customers")

        self.assertEqual(response.status_code, 401)

    def test_invalid_access_code_is_rejected(self):
        response = TestClient(self.app).post(
            "/api/v1/auth/session",
            json={
                "access_code": "incorrect-code",
                "reviewer_id": "analyst",
            },
        )

        self.assertEqual(response.status_code, 401)

    def test_session_cookie_is_http_only_and_same_site(self):
        client = TestClient(self.app)
        response = client.post(
            "/api/v1/auth/session",
            json={
                "access_code": ACCESS_CODE,
                "reviewer_id": "cookie-reviewer",
            },
        )

        cookie = response.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=strict", cookie)

    def test_session_endpoint_returns_reviewer_and_csrf(self):
        response = self.client.get("/api/v1/auth/session")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reviewer_id"], "commit15-reviewer")
        self.assertGreaterEqual(len(response.json()["csrf_token"]), 32)

    def test_tampered_and_expired_sessions_are_rejected(self):
        now = time.time()
        sessions = SessionManager(
            ACCESS_CODE,
            SESSION_SECRET,
            ttl_seconds=300,
            clock=lambda: now,
        )
        issued = sessions.authenticate(ACCESS_CODE, "expiry-reviewer")

        with self.assertRaises(InvalidSessionError):
            sessions.verify(f"{issued.token[:-1]}x")

        expired_sessions = SessionManager(
            ACCESS_CODE,
            SESSION_SECRET,
            ttl_seconds=300,
            clock=lambda: now + 301,
        )
        with self.assertRaisesRegex(InvalidSessionError, "Session expired"):
            expired_sessions.verify(issued.token)

    def test_customer_search_returns_warning_first_worklist(self):
        response = self.client.get("/api/v1/customers?limit=10")

        self.assertEqual(response.status_code, 200)
        customers = response.json()["customers"]
        self.assertEqual(len(customers), 10)
        self.assertEqual(customers[0]["warning_count"], 3)

    def test_customer_search_matches_id(self):
        response = self.client.get(f"/api/v1/customers?query={CUSTOMER_ID}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["customers"][0]["customer_id"], CUSTOMER_ID)

    def test_customer_360_reuses_pii_safe_tool_contracts(self):
        response = self.client.get(f"/api/v1/customers/{CUSTOMER_ID}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["profile"]["pii_included"])
        self.assertNotIn("email", payload["profile"])
        self.assertIn("purchase", payload["metrics"])
        self.assertIn(
            payload["campaign_eligibility"]["status"],
            {"BLOCKED", "REVIEW_REQUIRED"},
        )

    def test_unknown_customer_returns_404(self):
        response = self.client.get("/api/v1/customers/C9999999")

        self.assertEqual(response.status_code, 404)

    def test_write_endpoint_requires_csrf(self):
        response = self.client.post(
            "/api/v1/investigations",
            json={
                "customer_id": CUSTOMER_ID,
                "question": "Investigate current customer warning signals and evidence.",
            },
        )

        self.assertEqual(response.status_code, 403)

    def test_investigation_shapes_answer_sources_tools_timeline_and_metrics(self):
        payload = self.create_investigation()

        self.assertEqual(payload["customer_id"], CUSTOMER_ID)
        self.assertEqual(payload["risk_level"], "HIGH")
        self.assertEqual(payload["metrics"]["model"], "gpt-5.6-luna")
        self.assertEqual(payload["metrics"]["reasoning_effort"], "none")
        self.assertEqual(len(payload["tools"]), 2)
        self.assertTrue(payload["sources"][0]["cited"])
        self.assertIn("knowledge", payload["timeline"])

    def test_investigation_can_be_reloaded_by_owner(self):
        created = self.create_investigation()
        response = self.client.get(
            f"/api/v1/investigations/{created['investigation_id']}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), created)

    def test_investigation_is_not_visible_to_another_user(self):
        created = self.create_investigation()
        other = TestClient(self.app)
        self._login(other, "different-reviewer")

        response = other.get(f"/api/v1/investigations/{created['investigation_id']}")

        self.assertEqual(response.status_code, 404)

    def test_workspace_drafts_exact_synthetic_action_pending_approval(self):
        investigation = self.create_investigation()
        response = self.client.post(
            f"/api/v1/investigations/{investigation['investigation_id']}"
            "/support-action",
            headers=self.write_headers(),
            json={
                "priority": "HIGH",
                "reason": "The warning evidence merits a reviewed support follow-up.",
            },
        )

        self.assertEqual(response.status_code, 201, response.text)
        payload = response.json()
        self.assertEqual(payload["proposal"]["proposed_by"], "signaldesk_workspace")
        self.assertEqual(payload["run"]["status"], "PENDING_APPROVAL")
        self.assertEqual(
            payload["run"]["approval_request"]["action"]["action_type"],
            "CREATE_SUPPORT_CASE",
        )
        self.assertEqual(
            self.service._actions.store.event_count(payload["proposal"]["action_id"]),
            0,
        )

    def test_approved_action_executes_one_synthetic_event(self):
        investigation = self.create_investigation()
        draft = self.client.post(
            f"/api/v1/investigations/{investigation['investigation_id']}"
            "/support-action",
            headers=self.write_headers(),
            json={
                "priority": "MEDIUM",
                "reason": "Prepare this exact support follow-up for approval.",
            },
        ).json()
        action_id = draft["proposal"]["action_id"]

        response = self.client.post(
            f"/api/v1/actions/{action_id}/decision",
            headers=self.write_headers(),
            json={"decision": "APPROVED", "reason": "Evidence reviewed."},
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["run"]["status"], "EXECUTED")
        self.assertEqual(self.service._actions.store.event_count(action_id), 1)

    def test_rejected_action_creates_no_synthetic_event(self):
        investigation = self.create_investigation()
        draft = self.client.post(
            f"/api/v1/investigations/{investigation['investigation_id']}"
            "/support-action",
            headers=self.write_headers(),
            json={
                "priority": "LOW",
                "reason": "Create a separate low priority review candidate.",
            },
        ).json()
        action_id = draft["proposal"]["action_id"]

        response = self.client.post(
            f"/api/v1/actions/{action_id}/decision",
            headers=self.write_headers(),
            json={"decision": "REJECTED", "reason": "Follow-up is not needed."},
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["run"]["status"], "REJECTED")
        self.assertEqual(self.service._actions.store.event_count(action_id), 0)

    def test_completed_action_cannot_be_decided_again(self):
        investigation = self.create_investigation()
        draft = self.client.post(
            f"/api/v1/investigations/{investigation['investigation_id']}"
            "/support-action",
            headers=self.write_headers(),
            json={
                "priority": "LOW",
                "reason": "Prepare one reviewed support follow-up candidate.",
            },
        ).json()
        action_id = draft["proposal"]["action_id"]
        first = self.client.post(
            f"/api/v1/actions/{action_id}/decision",
            headers=self.write_headers(),
            json={"decision": "REJECTED", "reason": "No follow-up needed."},
        )

        repeated = self.client.post(
            f"/api/v1/actions/{action_id}/decision",
            headers=self.write_headers(),
            json={"decision": "APPROVED", "reason": "Try to reverse it."},
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(repeated.status_code, 409)
        self.assertEqual(self.service._actions.store.event_count(action_id), 0)


if __name__ == "__main__":
    unittest.main()
