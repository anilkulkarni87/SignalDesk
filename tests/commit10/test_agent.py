from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from evals.commit10.make_cases import build_cases, read_jsonl
from evals.commit10.metrics import build_report, evaluate_case
from evals.commit10.runner import read_case_ids, validate_frozen_cases
from src.agent.investigator import AgentConfig, AgentLimitError, CustomerInvestigator
from src.tools import CDPTools, ToolRegistry
from src.tools.schemas import CalculateCustomerMetricsInput


DATABASE = "data/warehouse/signaldesk.duckdb"


class FakeResponses:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return self.responses.pop(0)


def fake_usage():
    return SimpleNamespace(
        input_tokens=100,
        output_tokens=20,
        total_tokens=120,
        input_tokens_details=SimpleNamespace(cached_tokens=10),
        output_tokens_details=SimpleNamespace(reasoning_tokens=0),
    )


def fake_response(response_id, output, output_text=""):
    return SimpleNamespace(
        id=response_id,
        model="gpt-5.6-luna",
        status="completed",
        output=output,
        output_text=output_text,
        usage=fake_usage(),
    )


def answer_payload(customer_id="C0000001", *, limited=False):
    return {
        "customer_id": customer_id,
        "task_status": "LIMITED" if limited else "COMPLETED",
        "conclusion_code": "NO_WARNING_SIGNALS" if not limited else "INSUFFICIENT_EVIDENCE",
        "risk_level": "LOW" if not limited else "NOT_ASSESSED",
        "summary": "The available metrics do not show a material warning signal.",
        "evidence": [{
            "source_tool": "calculate_customer_metrics",
            "field": "purchase.purchase_decline_flag",
            "value": False,
            "interpretation": "The purchase warning flag is not set.",
        }],
        "policy_document_ids": [],
        "limitations": [],
    }


class AgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tools = CDPTools(DATABASE)
        cls.registry = ToolRegistry(cls.tools)

    @classmethod
    def tearDownClass(cls):
        cls.tools.close()

    def test_agent_exposes_only_six_read_tools(self):
        fake = FakeResponses([])
        agent = CustomerInvestigator(self.registry, responses_client=fake)
        names = {tool["name"] for tool in agent._tool_definitions}

        self.assertEqual(len(names), 6)
        self.assertNotIn("create_retention_recommendation", names)

    def test_agent_executes_tool_and_returns_structured_grounded_run(self):
        customer_id = "C0035947"
        metrics = self.tools.calculate_customer_metrics(
            CalculateCustomerMetricsInput(customer_id=customer_id)
        )
        payload = answer_payload(customer_id)
        payload["evidence"][0]["value"] = metrics.purchase["purchase_decline_flag"]
        fake = FakeResponses([
            fake_response("resp-1", [{
                "type": "function_call",
                "name": "calculate_customer_metrics",
                "arguments": json.dumps({"customer_id": customer_id}),
                "call_id": "call-1",
            }]),
            fake_response("resp-2", [], json.dumps(payload)),
        ])
        agent = CustomerInvestigator(self.registry, responses_client=fake)

        run = agent.investigate(
            customer_id,
            "Assess whether this customer has any material warning signals.",
        )

        self.assertEqual(run.answer.customer_id, customer_id)
        self.assertEqual(run.metrics.model_rounds, 2)
        self.assertEqual(run.metrics.tool_calls, 1)
        self.assertEqual(run.metrics.api_requests, 2)
        self.assertEqual(run.metrics.api_attempts, 2)
        self.assertEqual(run.metrics.api_retry_attempts, 0)
        self.assertTrue(run.tool_trace[0].success)
        second_input = fake.requests[1]["input"]
        self.assertTrue(any(item.get("type") == "function_call_output" for item in second_input))

    def test_agent_blocks_cross_customer_tool_arguments(self):
        customer_id = "C0035947"
        payload = answer_payload(customer_id, limited=True)
        fake = FakeResponses([
            fake_response("resp-1", [{
                "type": "function_call",
                "name": "calculate_customer_metrics",
                "arguments": json.dumps({"customer_id": "C0000002"}),
                "call_id": "call-1",
            }]),
            fake_response("resp-2", [], json.dumps(payload)),
        ])
        agent = CustomerInvestigator(self.registry, responses_client=fake)

        run = agent.investigate(customer_id, "Assess this customer's warning signals.")

        self.assertFalse(run.tool_trace[0].success)
        self.assertEqual(run.tool_trace[0].error_code, "CONFLICT")

    def test_agent_enforces_tool_call_limit(self):
        fake = FakeResponses([fake_response("resp-1", [
            {
                "type": "function_call",
                "name": "get_customer_profile",
                "arguments": json.dumps({"customer_id": "C0000001"}),
                "call_id": "call-1",
            },
            {
                "type": "function_call",
                "name": "calculate_customer_metrics",
                "arguments": json.dumps({"customer_id": "C0000001"}),
                "call_id": "call-2",
            },
        ])])
        agent = CustomerInvestigator(
            self.registry,
            config=AgentConfig(max_tool_calls=1),
            responses_client=fake,
        )

        with self.assertRaises(AgentLimitError):
            agent.investigate("C0000001", "Report this customer's current profile.")

    def test_evaluation_separates_selection_arguments_and_unnecessary_calls(self):
        case = {
            "expected_tools": ["calculate_customer_metrics"],
            "allowed_tools": ["calculate_customer_metrics"],
            "argument_rules": {
                "calculate_customer_metrics": {"customer_id": "C0000001"},
            },
            "expected_conclusion_code": "NO_WARNING_SIGNALS",
            "expected_risk_level": "LOW",
            "required_evidence": [{
                "source_tool": "calculate_customer_metrics",
                "field": "purchase.purchase_decline_flag",
                "value": False,
            }],
            "required_policy_families": [],
        }
        run = {
            "answer": answer_payload(),
            "tool_trace": [{
                "tool_name": "calculate_customer_metrics",
                "arguments": {"customer_id": "C0000001"},
                "success": True,
                "output": {"purchase": {"purchase_decline_flag": False}},
            }],
        }

        result = evaluate_case(case, run)

        self.assertTrue(result["correct_tools_selected"])
        self.assertTrue(result["correct_tool_arguments"])
        self.assertTrue(result["unnecessary_tools_empty"])
        self.assertTrue(result["summary_complete"])
        self.assertTrue(result["task_completed"])

    def test_evaluation_supports_canonical_array_paths(self):
        case = {
            "expected_tools": ["get_campaign_eligibility"],
            "allowed_tools": ["get_campaign_eligibility"],
            "argument_rules": {
                "get_campaign_eligibility": {"customer_id": "C0000001"},
            },
            "expected_conclusion_code": "CAMPAIGN_REVIEW_REQUIRED",
            "expected_risk_level": "NOT_ASSESSED",
            "required_evidence": [{
                "source_tool": "get_campaign_eligibility",
                "field": "channel_results[0].status",
                "value": "REVIEW_REQUIRED",
            }],
            "required_policy_families": [],
        }
        run = {
            "answer": {
                "task_status": "COMPLETED",
                "conclusion_code": "CAMPAIGN_REVIEW_REQUIRED",
                "risk_level": "NOT_ASSESSED",
                "summary": "Email can proceed to analyst review.",
                "evidence": [{
                    "source_tool": "get_campaign_eligibility",
                    "field": "channel_results[0].status",
                    "value": "REVIEW_REQUIRED",
                    "interpretation": "Email requires review.",
                }],
                "policy_document_ids": [],
            },
            "tool_trace": [{
                "tool_name": "get_campaign_eligibility",
                "arguments": {"customer_id": "C0000001"},
                "success": True,
                "output": {
                    "channel_results": [{"status": "REVIEW_REQUIRED"}],
                },
            }],
        }

        result = evaluate_case(case, run)

        self.assertTrue(result["all_evidence_grounded"])
        self.assertTrue(result["required_evidence_present"])

    def test_multi_family_policy_task_requires_separate_useful_searches(self):
        case = {
            "expected_tools": ["search_knowledge_base"],
            "allowed_tools": ["search_knowledge_base"],
            "argument_rules": {
                "search_knowledge_base": {
                    "required_families_across_calls": ["campaigns", "consent"],
                    "families_per_call_max": 1,
                    "minimum_calls": 2,
                    "top_k_min": 3,
                },
            },
            "expected_conclusion_code": "CAMPAIGN_REVIEW_REQUIRED",
            "expected_risk_level": "NOT_ASSESSED",
            "required_evidence": [{
                "source_tool": "search_knowledge_base",
                "field": "results[0].document_id",
                "value": "KB-CAMPAIGN",
            }],
            "required_policy_families": ["campaigns", "consent"],
        }
        answer = {
            "task_status": "COMPLETED",
            "conclusion_code": "CAMPAIGN_REVIEW_REQUIRED",
            "risk_level": "NOT_ASSESSED",
            "summary": "Campaign and consent policies both require analyst review.",
            "evidence": [
                {
                    "source_tool": "search_knowledge_base",
                    "field": "results[0].document_id",
                    "value": "KB-CAMPAIGN",
                    "interpretation": "Campaign policy was retrieved.",
                },
                {
                    "source_tool": "search_knowledge_base",
                    "field": "results[0].excerpt",
                    "value": "Campaign policy excerpt.",
                    "interpretation": "Campaign guidance used in the answer.",
                },
                {
                    "source_tool": "search_knowledge_base",
                    "field": "results[0].document_id",
                    "value": "KB-CONSENT",
                    "interpretation": "Consent policy was retrieved.",
                },
                {
                    "source_tool": "search_knowledge_base",
                    "field": "results[0].excerpt",
                    "value": "Consent policy excerpt.",
                    "interpretation": "Consent guidance used in the answer.",
                },
            ],
            "policy_document_ids": ["KB-CAMPAIGN", "KB-CONSENT"],
        }
        traces = [
            {
                "tool_name": "search_knowledge_base",
                "arguments": {
                    "query": "campaign contact rules",
                    "families": ["campaigns"],
                    "top_k": 3,
                },
                "success": True,
                "output": {"results": [{
                    "document_id": "KB-CAMPAIGN",
                    "family": "campaigns",
                    "excerpt": "Campaign policy excerpt.",
                }]},
            },
            {
                "tool_name": "search_knowledge_base",
                "arguments": {
                    "query": "consent suppression rules",
                    "families": ["consent"],
                    "top_k": 3,
                },
                "success": True,
                "output": {"results": [{
                    "document_id": "KB-CONSENT",
                    "family": "consent",
                    "excerpt": "Consent policy excerpt.",
                }]},
            },
        ]

        separated = evaluate_case(case, {"answer": answer, "tool_trace": traces})
        combined = evaluate_case(case, {
            "answer": answer,
            "tool_trace": [{
                **traces[0],
                "arguments": {
                    "query": "campaign consent rules",
                    "families": ["campaigns", "consent"],
                    "top_k": 3,
                },
                "output": {
                    "results": traces[0]["output"]["results"]
                    + traces[1]["output"]["results"],
                },
            }],
        })

        self.assertTrue(separated["correct_tool_arguments"])
        self.assertTrue(separated["unnecessary_tools_empty"])
        self.assertTrue(separated["all_policy_citations_evidenced"])
        self.assertTrue(separated["task_completed"])
        self.assertFalse(combined["correct_tool_arguments"])
        self.assertFalse(combined["task_completed"])

    def test_policy_citation_requires_document_id_and_excerpt_evidence(self):
        case = {
            "expected_tools": ["search_knowledge_base"],
            "allowed_tools": ["search_knowledge_base"],
            "argument_rules": {
                "search_knowledge_base": {
                    "required_families_across_calls": ["support"],
                },
            },
            "expected_conclusion_code": "SUPPORT_ATTENTION",
            "expected_risk_level": "MEDIUM",
            "required_evidence": [],
            "required_policy_families": ["support"],
        }
        answer = {
            "task_status": "COMPLETED",
            "conclusion_code": "SUPPORT_ATTENTION",
            "risk_level": "MEDIUM",
            "summary": "Current support policy requires analyst review.",
            "evidence": [],
            "policy_document_ids": ["KB-SUPPORT"],
        }
        traces = [{
            "tool_name": "search_knowledge_base",
            "arguments": {"families": ["support"]},
            "success": True,
            "output": {"results": [{
                "document_id": "KB-SUPPORT",
                "family": "support",
                "excerpt": "Escalate uncertain cases for analyst review.",
            }]},
        }]

        result = evaluate_case(case, {"answer": answer, "tool_trace": traces})

        self.assertTrue(result["all_policy_citations_retrieved"])
        self.assertFalse(result["all_policy_citations_evidenced"])
        self.assertFalse(result["task_completed"])

    def test_v3_cohort_selects_25_unique_frozen_cases(self):
        frozen_ids = {
            case["case_id"]
            for case in read_jsonl(Path("evals/commit10/cases.jsonl"))
        }
        cohort_ids = read_case_ids(Path("evals/commit10/v3_cohort_case_ids.txt"))

        self.assertEqual(len(cohort_ids), 25)
        self.assertEqual(len(set(cohort_ids)), 25)
        self.assertTrue(set(cohort_ids).issubset(frozen_ids))

    def test_v4_cohort_selects_only_the_five_campaign_cases(self):
        frozen = read_jsonl(Path("evals/commit10/cases.jsonl"))
        frozen_by_id = {case["case_id"]: case for case in frozen}
        cohort_ids = read_case_ids(Path("evals/commit10/v4_campaign_case_ids.txt"))

        self.assertEqual(len(cohort_ids), 5)
        self.assertEqual(len(set(cohort_ids)), 5)
        self.assertTrue(all(
            frozen_by_id[case_id]["task_type"] == "campaign_readiness"
            for case_id in cohort_ids
        ))

    def test_report_separates_policy_metrics_from_non_policy_cases(self):
        def row(case_id, families, evidenced):
            return {
                "api_success": True,
                "case": {
                    "case_id": case_id,
                    "task_type": "policy" if families else "non_policy",
                    "required_policy_families": families,
                },
                "evaluation": {
                    "all_policy_citations_retrieved": True,
                    "all_policy_citations_evidenced": evidenced,
                    "required_policy_families_cited": evidenced,
                    "task_completed": evidenced,
                },
                "run": {"metrics": {
                    "model": "gpt-5.6-luna",
                    "prompt_version": "test",
                    "reasoning_effort": "none",
                    "latency_seconds": 1.0,
                    "tool_calls": 1,
                    "api_requests": 2,
                    "api_retry_attempts": 0,
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "estimated_cost_usd": 0.001,
                }},
            }

        report = build_report([
            row("policy", ["support"], False),
            row("non-policy", [], True),
        ])

        self.assertEqual(report["all_policy_citations_evidenced_rate_pct"], 50.0)
        self.assertEqual(report["policy_tasks"]["cases"], 1)
        self.assertEqual(
            report["policy_tasks"]["all_policy_citations_evidenced_rate_pct"],
            0.0,
        )

    def test_frozen_cases_have_expected_distribution_and_unique_customers(self):
        frozen = read_jsonl(Path("evals/commit10/cases.jsonl"))
        validate_frozen_cases(frozen)

        generated = build_cases(
            read_jsonl(Path("evals/commit05/cases.jsonl")),
            self.tools,
        )
        self.assertEqual(frozen, generated)

    def test_frozen_case_validation_rejects_duplicate_subject(self):
        cases = read_jsonl(Path("evals/commit10/cases.jsonl"))
        cases[1]["customer_id"] = cases[0]["customer_id"]

        with self.assertRaisesRegex(ValueError, "50 unique customers"):
            validate_frozen_cases(cases)


if __name__ == "__main__":
    unittest.main()
