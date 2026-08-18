from __future__ import annotations

import unittest
from dataclasses import replace

from pydantic import ValidationError

from src.tools import CDPTools, ToolRegistry
from src.tools.schemas import (
    CreateRetentionRecommendationInput,
    GetCampaignEligibilityInput,
    GetCustomerEventsInput,
    GetCustomerProfileInput,
    GetPurchaseHistoryInput,
    SearchKnowledgeBaseInput,
    ToolCallResult,
    ToolErrorDetail,
)


DATABASE = "data/warehouse/signaldesk.duckdb"


class CDPToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tools = CDPTools(DATABASE)
        cls.registry = ToolRegistry(cls.tools)

    @classmethod
    def tearDownClass(cls):
        cls.tools.close()

    def test_registry_exposes_seven_strict_side_effect_free_contracts(self):
        definitions = self.registry.definitions()

        self.assertEqual(len(definitions), 7)
        self.assertEqual(len({definition["name"] for definition in definitions}), 7)
        self.assertTrue(all(item["side_effects"] == "none" for item in definitions))
        self.assertTrue(all(
            item["input_schema"].get("additionalProperties") is False
            for item in definitions
        ))

    def test_profile_is_pii_safe_and_uses_semantic_as_of_time(self):
        profile = self.tools.get_customer_profile(
            GetCustomerProfileInput(customer_id="C0000001")
        )
        payload = profile.model_dump()

        self.assertEqual(profile.customer_id, "C0000001")
        self.assertFalse(profile.pii_included)
        self.assertIn("as_of_ts", payload)
        self.assertNotIn("email", payload)
        self.assertNotIn("phone", payload)

    def test_events_are_bounded_filtered_and_reverse_chronological(self):
        result = self.tools.get_customer_events(GetCustomerEventsInput(
            customer_id="C0000001",
            days=90,
            limit=5,
            event_types=["product_view"],
        ))

        self.assertLessEqual(result.returned_count, 5)
        self.assertEqual(result.event_types, ["product_view"])
        self.assertTrue(all(event.event_type == "product_view" for event in result.events))
        timestamps = [event.event_timestamp for event in result.events]
        self.assertEqual(timestamps, sorted(timestamps, reverse=True))
        self.assertEqual(result.truncated, result.total_count > result.returned_count)

    def test_purchase_history_includes_product_line_evidence(self):
        result = self.tools.get_purchase_history(GetPurchaseHistoryInput(
            customer_id="C0000001",
            days=730,
            limit=10,
        ))

        self.assertLessEqual(result.returned_count, 10)
        self.assertTrue(result.orders)
        self.assertTrue(all(order.items for order in result.orders))
        self.assertTrue(all(item.category for order in result.orders for item in order.items))

    def test_knowledge_search_returns_only_requested_authoritative_family(self):
        result = self.tools.search_knowledge_base(SearchKnowledgeBaseInput(
            query="email opt out suppression",
            top_k=3,
            families=["consent"],
        ))

        self.assertEqual(result.returned_count, 3)
        self.assertEqual(result.retrieval_method, "lexical_current_approved")
        self.assertTrue(all(item.family == "consent" for item in result.results))
        self.assertTrue(all(item.status == "CURRENT" for item in result.results))
        self.assertTrue(all(item.authority == "APPROVED" for item in result.results))

    def test_metrics_preserve_nulls_and_customer_360_provenance(self):
        result = self.registry.execute(
            "calculate_customer_metrics",
            {"customer_id": "C0000001"},
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output["provenance"], "customer_360")
        self.assertIn("purchase_change_pct", result.output["purchase"])
        self.assertIn("support_attention_flag", result.output["support"])

    def test_campaign_eligibility_never_claims_final_eligibility(self):
        active = self.tools.get_campaign_eligibility(
            GetCampaignEligibilityInput(customer_id="C0000001")
        )
        closed = self.tools.get_campaign_eligibility(
            GetCampaignEligibilityInput(customer_id="C0000006")
        )

        self.assertIn(active.status, {"BLOCKED", "REVIEW_REQUIRED"})
        self.assertTrue(all(
            item.status in {"BLOCKED", "REVIEW_REQUIRED"}
            for item in active.channel_results
        ))
        self.assertEqual(closed.status, "BLOCKED")

    def test_recommendation_is_deterministic_draft_only_and_evidence_bound(self):
        request = CreateRetentionRecommendationInput(
            customer_id="C0000001",
            recommendation="INVESTIGATE",
            rationale="Review recent purchase and engagement evidence before deciding.",
            evidence_features=["purchase_decline_flag", "engagement_decline_flag"],
            policy_document_ids=["KB-00779"],
        )
        first = self.tools.create_retention_recommendation(request)
        second = self.tools.create_retention_recommendation(request)

        self.assertEqual(first.recommendation_id, second.recommendation_id)
        self.assertEqual(first.status, "DRAFT")
        self.assertTrue(first.requires_human_approval)
        self.assertFalse(first.execution_allowed)
        self.assertFalse(first.persisted)
        self.assertTrue(first.limitations)
        self.assertEqual(
            [evidence.feature for evidence in first.evidence],
            request.evidence_features,
        )

    def test_registry_returns_structured_validation_not_found_and_conflict_errors(self):
        validation = self.registry.execute(
            "get_customer_events",
            {"customer_id": "bad", "days": 0},
        )
        missing = self.registry.execute(
            "get_customer_profile",
            {"customer_id": "C9999999"},
        )
        conflict = self.registry.execute(
            "create_retention_recommendation",
            {
                "customer_id": "C0000006",
                "recommendation": "RETENTION_OFFER",
                "rationale": "Offer should not be drafted when every channel is blocked.",
                "evidence_features": ["customer_status"],
                "policy_document_ids": ["KB-00779"],
            },
        )

        self.assertEqual(validation.error.code, "VALIDATION_ERROR")
        self.assertEqual(missing.error.code, "NOT_FOUND")
        self.assertEqual(conflict.error.code, "CONFLICT")

    def test_registry_rejects_unknown_tools_extra_arguments_and_unknown_policy(self):
        unknown_tool = self.registry.execute("drop_database", {})
        extra = self.registry.execute(
            "get_customer_profile",
            {"customer_id": "C0000001", "include_email": True},
        )
        unknown_policy = self.registry.execute(
            "create_retention_recommendation",
            {
                "customer_id": "C0000001",
                "recommendation": "INVESTIGATE",
                "rationale": "Review evidence but do not execute an intervention.",
                "evidence_features": ["purchase_decline_flag"],
                "policy_document_ids": ["KB-99999"],
            },
        )

        self.assertEqual(unknown_tool.error.code, "UNKNOWN_TOOL")
        self.assertEqual(extra.error.code, "VALIDATION_ERROR")
        self.assertEqual(unknown_policy.error.code, "NOT_FOUND")

    def test_result_envelope_rejects_inconsistent_success_and_failure_states(self):
        with self.assertRaises(ValidationError):
            ToolCallResult(
                tool_name="get_customer_profile",
                success=True,
                error=ToolErrorDetail(code="INTERNAL_ERROR", message="unexpected"),
                latency_ms=1,
            )
        with self.assertRaises(ValidationError):
            ToolCallResult(
                tool_name="get_customer_profile",
                success=False,
                output={"customer_id": "C0000001"},
                latency_ms=1,
            )

    def test_registry_classifies_handler_type_error_as_internal(self):
        tool_name = "get_customer_profile"
        original = self.registry._specs[tool_name]

        def broken_handler(_request):
            raise TypeError("implementation defect")

        self.registry._specs[tool_name] = replace(original, handler=broken_handler)
        try:
            result = self.registry.execute(tool_name, {"customer_id": "C0000001"})
        finally:
            self.registry._specs[tool_name] = original

        self.assertFalse(result.success)
        self.assertEqual(result.error.code, "INTERNAL_ERROR")
        self.assertEqual(result.error.message, "Tool execution failed")


if __name__ == "__main__":
    unittest.main()
