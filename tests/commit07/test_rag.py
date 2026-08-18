from __future__ import annotations

import json
import unittest

from pydantic import ValidationError

from evals.commit07.compare import metric_transition
from evals.commit07.make_cases import build_cases, read_jsonl
from evals.commit07.metrics import build_report
from evals.commit07.runner import citation_is_grounded, select_cases
from src.llm.customer_store import CustomerStore
from src.llm.policy_context import build_policy_context, build_policy_quotes
from src.llm.policy_schemas import (
    ModelPolicyGroundedAssessment,
    PolicyIntentSourceSelection,
    model_assessment_schema,
    resolve_policy_assessment,
)
from src.llm.prompt_versions import v6
from src.retrieval.embeddings import EmbeddingRun
from src.retrieval.query_planner import (
    PlannedPolicyQuery,
    PolicyRetrievalResult,
    VectorPolicyRetriever,
    expected_families,
)
from src.retrieval.vector_store import VectorSearchResult


def policy_result(**overrides) -> PolicyRetrievalResult:
    values = {
        "chunk_id": "KB-1::chunk-000",
        "document_id": "KB-1",
        "title": "Policy",
        "family": "retention",
        "document_type": "POLICY",
        "status": "CURRENT",
        "authority": "APPROVED",
        "topic": "when no action is appropriate",
        "score": 0.9,
        "best_query_rank": 1,
        "content": "Human review remains required before an intervention.",
        "source_path": "policy.md",
        "matched_queries": ["retention review"],
        "retrieval_reasons": ["no warning signals"],
    }
    values.update(overrides)
    return PolicyRetrievalResult(**values)


def model_assessment(**overrides) -> ModelPolicyGroundedAssessment:
    values = {
        "risk_level": "LOW",
        "summary": "No warning signal is present.",
        "evidence": [{
            "feature": "purchase_decline_flag",
            "interpretation": "The curated flag is false.",
        }],
        "recommended_investigation": ["NO_FURTHER_INVESTIGATION"],
        "limitations": [],
        "policy_intent_sources": {
            "I01": {
                "quote_ids": ["Q001"],
                "relevance": "Requires human review.",
                "cited_policy_point": "Human review remains required.",
            },
        },
        "unsupported_policy_claims": [],
    }
    values.update(overrides)
    return ModelPolicyGroundedAssessment(**values)


class CaseTests(unittest.TestCase):
    def test_commit05_inputs_expand_to_one_hundred_questions(self):
        source_cases = list(read_jsonl("evals/commit05/cases.jsonl"))
        store = CustomerStore("data/warehouse/signaldesk.duckdb")

        cases = build_cases(source_cases, store)

        self.assertEqual(len(cases), 100)
        self.assertEqual(len({case["case_id"] for case in cases}), 100)
        self.assertEqual(
            {case["question_type"] for case in cases},
            {"risk_investigation", "policy_guardrails"},
        )

    def test_targeted_case_selection_preserves_frozen_order(self):
        cases = [
            {"case_id": "case_01"},
            {"case_id": "case_02"},
            {"case_id": "case_03"},
        ]

        selected = select_cases(
            cases,
            case_ids=["case_03", "case_01"],
            case_ids_file=None,
            limit=None,
        )

        self.assertEqual(
            [case["case_id"] for case in selected],
            ["case_01", "case_03"],
        )


class PlannerTests(unittest.TestCase):
    def test_no_warning_customer_keeps_retention_guidance_with_opt_out(self):
        snapshot = {
            "purchase_decline_flag": False,
            "engagement_decline_flag": False,
            "support_attention_flag": False,
            "recent_subscription_cancellation_flag": False,
            "email_opted_in": False,
            "sms_opted_in": True,
            "push_opted_in": True,
        }

        self.assertEqual(expected_families(snapshot), ["consent", "retention"])


class ContextTests(unittest.TestCase):
    def test_context_rejects_non_authoritative_source(self):
        with self.assertRaises(ValueError):
            build_policy_context([
                policy_result(status="SUPERSEDED"),
            ])

    def test_context_enforces_budget_without_partial_json(self):
        first = policy_result()
        second = policy_result(
            chunk_id="KB-2::chunk-000",
            document_id="KB-2",
            content="x" * 2_000,
        )

        context = build_policy_context([first, second], max_characters=1_000)

        self.assertEqual(context.document_ids, ["KB-1"])
        self.assertLessEqual(context.character_count, 1_000)

    def test_context_exposes_runtime_intents_and_stable_quote_ids(self):
        planned_query = PlannedPolicyQuery(
            reason="support_attention_flag is true",
            query="open support case support escalation handoff",
            expected_families=["support"],
            expected_doc_ids=[],
        )

        context = build_policy_context(
            [policy_result(family="support")],
            planned_queries=[planned_query],
        )
        payload = json.loads(context.json_text)

        self.assertEqual(
            payload["required_policy_intents"][0]["required_families"],
            ["support"],
        )
        self.assertEqual(
            payload["required_policy_intents"][0]["intent_id"],
            "I01",
        )
        self.assertEqual(
            payload["sources"][0]["quotes"][0]["quote_id"],
            "Q001",
        )
        self.assertEqual(context.intent_quote_ids, {"I01": ["Q001"]})

    def test_quote_segments_are_bounded_and_source_grounded(self):
        result = policy_result(content="A " + ("long policy phrase " * 30))

        quotes = build_policy_quotes(result)

        self.assertGreater(len(quotes), 1)
        self.assertTrue(all(len(quote.text) <= 320 for quote in quotes))
        normalized_source = " ".join(result.content.split())
        self.assertTrue(all(
            " ".join(quote.text.split()) in normalized_source
            for quote in quotes
        ))

    def test_context_quote_ids_are_short_unique_and_contiguous(self):
        context = build_policy_context([
            policy_result(),
            policy_result(
                chunk_id="KB-2::chunk-000",
                document_id="KB-2",
                content="A second policy sentence.",
            ),
        ])

        self.assertEqual(
            list(context.quotes_by_id),
            ["Q001", "Q002"],
        )


class CitationTests(unittest.TestCase):
    def test_quote_resolution_attaches_document_and_exact_excerpt(self):
        result = policy_result()
        quote = build_policy_quotes(result)[0]
        assessment = model_assessment(policy_intent_sources={
            "I01": PolicyIntentSourceSelection(
                quote_ids=[quote.quote_id],
                relevance="Controls intervention execution.",
                cited_policy_point="Human review is required.",
            ),
        })

        resolved = resolve_policy_assessment(
            assessment,
            {quote.quote_id: quote},
            {"I01": [quote.quote_id]},
        )
        citation = resolved.policy_sources[0]

        self.assertEqual(citation.document_id, "KB-1")
        self.assertEqual(citation.supporting_excerpt, quote.text)
        self.assertTrue(citation_is_grounded(citation, {"KB-1": result}))
        self.assertFalse(citation_is_grounded(citation, {}))

    def test_quote_resolution_rejects_unknown_identifier(self):
        assessment = model_assessment()

        with self.assertRaisesRegex(ValueError, "unknown policy quote ID"):
            resolve_policy_assessment(
                assessment,
                {},
                {"I01": ["Q001"]},
            )

    def test_schema_rejects_blank_unsupported_claim(self):
        with self.assertRaises(ValidationError):
            model_assessment(unsupported_policy_claims=[" "])

    def test_schema_rejects_duplicate_quote_ids(self):
        source = {
            "quote_ids": ["Q001"],
            "relevance": "Controls intervention execution.",
            "cited_policy_point": "Human review is required.",
        }

        with self.assertRaises(ValidationError):
            model_assessment(policy_intent_sources={
                "I01": source,
                "I02": source,
            })

    def test_response_schema_enumerates_only_available_quote_ids(self):
        intent_quote_ids = {
            "I01": ["Q002", "Q001"],
            "I02": ["Q003"],
        }

        schema = model_assessment_schema(intent_quote_ids)
        intent_schema = schema["properties"]["policy_intent_sources"]
        quote_id_schema = intent_schema["properties"]["I01"][
            "properties"
        ]["quote_ids"]["items"]

        self.assertEqual(
            intent_schema["required"],
            ["I01", "I02"],
        )
        self.assertEqual(
            quote_id_schema["enum"],
            ["Q001", "Q002"],
        )


class PromptTests(unittest.TestCase):
    def test_v6_distinguishes_unknown_effect_from_zero_effect(self):
        self.assertIn(
            "does not prove\n  the effect is zero",
            v6.SYSTEM_INSTRUCTIONS,
        )
        self.assertIn("under 300 characters", v6.SYSTEM_INSTRUCTIONS)


class FakeEmbedder:
    def __init__(self):
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        vectors = [[float(index + 1), 0.0] for index, _ in enumerate(texts)]
        return EmbeddingRun(
            vectors=vectors,
            model="fake",
            dimensions=2,
            input_count=len(texts),
            input_tokens=len(texts),
        )


class FakeVectorStore:
    def __init__(self):
        self.calls = 0

    def search(self, query_vector, **kwargs):
        self.calls += 1
        family = "consent" if self.calls % 2 == 1 else "retention"
        document_id = f"KB-{self.calls}"
        return [VectorSearchResult(
            chunk_id=f"{document_id}::chunk-000",
            document_id=document_id,
            title="Policy",
            family=family,
            document_type="POLICY",
            status="CURRENT",
            authority="APPROVED",
            topic="topic",
            score=0.9,
            content="Policy content.",
            source_path="policy.md",
        )]


class RetrieverTests(unittest.TestCase):
    def test_retriever_caches_repeated_planned_query_embeddings(self):
        embedder = FakeEmbedder()
        retriever = VectorPolicyRetriever(
            embedder=embedder,
            vector_store=FakeVectorStore(),
        )
        snapshot = {
            "purchase_decline_flag": False,
            "engagement_decline_flag": False,
            "support_attention_flag": False,
            "recent_subscription_cancellation_flag": False,
            "email_opted_in": False,
            "sms_opted_in": True,
            "push_opted_in": True,
        }

        first = retriever.retrieve(snapshot)
        second = retriever.retrieve(snapshot)

        self.assertEqual(embedder.calls, 1)
        self.assertEqual(len(first), 2)
        self.assertEqual(len(second), 2)


class MetricsTests(unittest.TestCase):
    def test_report_keeps_retrieval_generation_and_citation_metrics_separate(self):
        row = {
            "api_success": True,
            "api_attempts": 1,
            "first_attempt_api_success": True,
            "schema_valid": True,
            "citation_resolution_valid": True,
            "case": {
                "case_id": "case_01",
                "customer_id": "C1",
                "question_type": "risk_investigation",
            },
            **{
                metric: True
                for metric in (
                    "risk_correct",
                    "required_evidence_all_present",
                    "required_evidence_any_present",
                    "answer_correct",
                    "expected_policy_docs_retrieved",
                    "expected_policy_families_retrieved",
                    "all_citations_retrieved",
                    "all_citation_excerpts_grounded",
                    "expected_policy_docs_cited",
                    "expected_policy_families_cited",
                    "unsupported_policy_claims_empty",
                )
            },
            "citation_count": 2,
            "citation_grounded_count": 2,
            "metrics": {
                "retrieval_latency_seconds": 0.1,
                "generation_latency_seconds": 1.0,
                "total_latency_seconds": 1.1,
                "input_tokens": 100,
                "cached_input_tokens": 10,
                "output_tokens": 50,
                "reasoning_tokens": 0,
                "total_tokens": 150,
                "estimated_cost_usd": 0.01,
            },
        }

        report = build_report([row])

        self.assertEqual(report["answer_correct_rate_pct"], 100.0)
        self.assertEqual(report["citation_precision_pct"], 100.0)
        self.assertEqual(report["first_attempt_api_success_rate_pct"], 100.0)
        self.assertEqual(report["api_retry_attempts_total"], 0)
        self.assertEqual(report["latency_seconds"]["retrieval"]["mean"], 0.1)
        self.assertEqual(report["reasoning_tokens_total"], 0)

    def test_comparison_reports_improvements_and_regressions(self):
        baseline = {
            "case_01": {"answer_correct": True},
            "case_02": {"answer_correct": False},
        }
        candidate = {
            "case_01": {"answer_correct": False},
            "case_02": {"answer_correct": True},
        }

        transition = metric_transition(
            baseline,
            candidate,
            "answer_correct",
        )

        self.assertEqual(transition["improvements"], ["case_02"])
        self.assertEqual(transition["regressions"], ["case_01"])


if __name__ == "__main__":
    unittest.main()
