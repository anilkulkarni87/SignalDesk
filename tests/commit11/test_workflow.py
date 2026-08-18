from __future__ import annotations

import json
import unittest
from pathlib import Path

from evals.commit11.make_scenarios import (
    build_scenarios,
    read_jsonl,
    validate_scenarios,
)
from evals.commit11.runner import (
    mark_empty_policy_metrics_not_applicable,
    select_cases,
)
from src.agent import AgentConfig
from src.agent.prompts import PROMPT_VERSION
from src.tools import CDPTools, ToolRegistry
from src.workflow import LangGraphCustomerInvestigator, WorkflowExecutionError
from src.workflow.investigator import WORKFLOW_VERSION
from tests.commit10.test_agent import (
    FakeResponses,
    answer_payload,
    fake_response,
)


DATABASE = "data/warehouse/signaldesk.duckdb"


class FailOnceResponses(FakeResponses):
    def __init__(self, responses):
        super().__init__(responses)
        self.failed = False

    def create(self, **kwargs):
        if not self.failed:
            self.failed = True
            raise RuntimeError("injected node failure")
        return super().create(**kwargs)


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tools = CDPTools(DATABASE)
        cls.registry = ToolRegistry(cls.tools)

    @classmethod
    def tearDownClass(cls):
        cls.tools.close()

    def test_graph_routes_each_tool_family_and_finishes_analysis_only(self):
        customer_id = "C0035947"
        fake = FakeResponses([
            fake_response("resp-tools", [
                {
                    "type": "function_call",
                    "name": "calculate_customer_metrics",
                    "arguments": json.dumps({"customer_id": customer_id}),
                    "call_id": "call-profile",
                },
                {
                    "type": "function_call",
                    "name": "get_customer_events",
                    "arguments": json.dumps({"customer_id": customer_id, "limit": 5}),
                    "call_id": "call-events",
                },
                {
                    "type": "function_call",
                    "name": "search_knowledge_base",
                    "arguments": json.dumps({
                        "query": "support escalation review",
                        "families": ["support"],
                        "top_k": 3,
                    }),
                    "call_id": "call-knowledge",
                },
            ]),
            fake_response(
                "resp-answer",
                [],
                json.dumps(answer_payload(customer_id)),
            ),
        ])
        workflow = LangGraphCustomerInvestigator(
            self.registry,
            responses_client=fake,
        )

        run = workflow.investigate(
            customer_id,
            "Assess this customer and retrieve the relevant support policy.",
            thread_id="route-test",
        )

        self.assertEqual(
            run.workflow.routed_tool_nodes,
            ["profile", "events", "knowledge"],
        )
        self.assertEqual(run.metrics.tool_calls, 3)
        self.assertGreater(run.workflow.checkpoint_count, len(run.workflow.transitions))
        self.assertEqual(run.workflow.recommendation, "ANALYSIS_ONLY")
        self.assertFalse(run.workflow.approval_required)
        self.assertFalse(run.workflow.action_executed)
        self.assertNotIn("execute_action", run.workflow.transitions)

    def test_checkpoint_resume_restarts_at_failed_node(self):
        customer_id = "C0035947"
        fake = FailOnceResponses([
            fake_response(
                "resp-answer",
                [],
                json.dumps(answer_payload(customer_id)),
            ),
        ])
        workflow = LangGraphCustomerInvestigator(
            self.registry,
            responses_client=fake,
        )

        with self.assertRaisesRegex(RuntimeError, "injected node failure"):
            workflow.start(
                customer_id,
                "Assess whether this customer has warning signals.",
                thread_id="recovery-test",
            )

        snapshot = workflow.graph.get_state(workflow._config("recovery-test"))
        self.assertEqual(snapshot.next, ("reason_about_case",))

        run = workflow.resume("recovery-test")

        self.assertEqual(run.workflow.resume_count, 1)
        self.assertEqual(run.workflow.transitions.count("interpret_request"), 1)
        self.assertEqual(run.workflow.transitions.count("resolve_customer"), 1)
        self.assertEqual(run.answer.customer_id, customer_id)

    def test_cross_customer_tool_call_remains_blocked(self):
        customer_id = "C0035947"
        fake = FakeResponses([
            fake_response("resp-tools", [{
                "type": "function_call",
                "name": "calculate_customer_metrics",
                "arguments": json.dumps({"customer_id": "C0000002"}),
                "call_id": "call-conflict",
            }]),
            fake_response(
                "resp-answer",
                [],
                json.dumps(answer_payload(customer_id, limited=True)),
            ),
        ])
        workflow = LangGraphCustomerInvestigator(
            self.registry,
            responses_client=fake,
        )

        run = workflow.investigate(
            customer_id,
            "Assess whether this customer has warning signals.",
            thread_id="binding-test",
        )

        self.assertFalse(run.tool_trace[0].success)
        self.assertEqual(run.tool_trace[0].error_code, "CONFLICT")

    def test_resume_requires_an_existing_checkpoint(self):
        workflow = LangGraphCustomerInvestigator(
            self.registry,
            responses_client=FakeResponses([]),
        )

        with self.assertRaisesRegex(WorkflowExecutionError, "No checkpoint"):
            workflow.resume("missing-thread")

    def test_model_prompt_and_reasoning_are_frozen(self):
        config = AgentConfig()

        self.assertEqual(config.model, "gpt-5.6-luna")
        self.assertEqual(config.reasoning_effort, "none")
        self.assertEqual(PROMPT_VERSION, "commit10_v4_campaign_evidence_budget")
        self.assertEqual(
            WORKFLOW_VERSION,
            "commit11_v1_explicit_stateful_investigation",
        )

    def test_scenario_manifest_has_two_modes_for_each_frozen_case(self):
        baseline = read_jsonl(
            Path("evals/commit10/reports/v4_full_results.jsonl")
        )
        scenarios = build_scenarios(baseline)

        validate_scenarios(scenarios)
        self.assertEqual(len(scenarios), 100)
        self.assertEqual(
            {item["mode"] for item in scenarios},
            {"standard", "checkpoint_recovery"},
        )

    def test_cross_category_selector_preserves_frozen_order(self):
        cases = read_jsonl(Path("evals/commit10/cases.jsonl"))

        selected = select_cases(
            cases,
            case_ids=[],
            case_id_file=Path("evals/commit11/cross_category_case_ids.txt"),
            limit=None,
        )

        self.assertEqual(len(selected), 6)
        self.assertEqual(len({case["task_type"] for case in selected}), 6)
        frozen_positions = {case["case_id"]: index for index, case in enumerate(cases)}
        self.assertEqual(
            [frozen_positions[case["case_id"]] for case in selected],
            sorted(frozen_positions[case["case_id"]] for case in selected),
        )

    def test_selector_rejects_unknown_case_id(self):
        cases = read_jsonl(Path("evals/commit10/cases.jsonl"))

        with self.assertRaisesRegex(ValueError, "Unknown case IDs"):
            select_cases(
                cases,
                case_ids=["not-a-frozen-case"],
                case_id_file=None,
                limit=None,
            )

    def test_empty_policy_rates_are_reported_as_not_applicable(self):
        report = {
            "all_policy_citations_retrieved_rate_pct": 100.0,
            "all_policy_citations_evidenced_rate_pct": 100.0,
            "required_policy_families_cited_rate_pct": 100.0,
            "policy_tasks": {
                "cases": 0,
                "all_policy_citations_retrieved_rate_pct": 0.0,
                "all_policy_citations_evidenced_rate_pct": 0.0,
                "required_policy_families_cited_rate_pct": 0.0,
                "task_completed_rate_pct": 0.0,
            },
        }

        mark_empty_policy_metrics_not_applicable(report)

        self.assertIsNone(report["all_policy_citations_retrieved_rate_pct"])
        self.assertIsNone(report["policy_tasks"]["task_completed_rate_pct"])


if __name__ == "__main__":
    unittest.main()
