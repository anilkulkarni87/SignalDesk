from __future__ import annotations

import json
import unittest
from pathlib import Path

from evals.commit08.matrix import (
    build_treatment_metadata,
    index_specs,
    metadata_matches,
    selection_analysis,
    validate_contract,
)
from evals.commit08.metrics import (
    score_case,
    treatment_sha256,
    validate_frozen_inputs,
)
from src.retrieval.documents import KnowledgeDocument, load_documents
from src.retrieval.ranking import reciprocal_rank_fusion, rerank_vector_candidates
from src.retrieval.vector_store import PgVectorStore, validate_sql_identifier


CONTRACT_PATH = Path("evals/commit08/experiment_contract.json")


def document(
    document_id: str,
    *,
    family: str,
    topic: str,
    status: str = "CURRENT",
    authority: str = "APPROVED",
) -> KnowledgeDocument:
    return KnowledgeDocument(
        document_id=document_id,
        title=f"{document_id} title",
        family=family,
        document_type="POLICY",
        status=status,
        version="1.0",
        effective_date="2026-08-01",
        authority=authority,
        path=Path(f"{document_id}.md"),
        body="Policy body",
        metadata={"topic": topic},
    )


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def test_contract_and_frozen_inputs_are_valid(self):
        validate_contract(self.contract)
        validate_frozen_inputs(self.contract)

    def test_contract_covers_each_roadmap_variable(self):
        experiments = {
            item["experiment_id"]: item for item in self.contract["experiments"]
        }

        self.assertIn("vector_unfiltered", experiments)
        self.assertIn("vector_baseline", experiments)
        self.assertIn("vector_small_chunks", experiments)
        self.assertIn("vector_no_overlap", experiments)
        self.assertIn("vector_large_chunks", experiments)
        self.assertIn("hybrid_rrf", experiments)
        self.assertIn("vector_lexical_rerank", experiments)
        self.assertEqual(len(index_specs(list(experiments.values()))), 4)

    def test_metadata_match_requires_every_frozen_value(self):
        expected = {"max_words": 220, "overlap_words": 40}

        self.assertTrue(metadata_matches({**expected, "extra": True}, expected))
        self.assertFalse(metadata_matches({"max_words": 220}, expected))

    def test_overlap_variants_have_the_same_treatment_fingerprint(self):
        metadata = build_treatment_metadata(
            self.contract,
            self.contract["experiments"],
            load_documents(self.contract["corpus_dir"]),
        )

        self.assertEqual(
            metadata["vector_baseline"]["chunk_content_sha256"],
            metadata["vector_no_overlap"]["chunk_content_sha256"],
        )
        self.assertEqual(
            metadata["vector_baseline"]["treatment_sha256"],
            metadata["vector_no_overlap"]["treatment_sha256"],
        )

    def test_selection_excludes_an_equivalent_timing_candidate(self):
        summaries = {
            experiment_id: {
                "experiment_id": experiment_id,
                "filter_current_approved": True,
                "current_approved_result_rate_at_5_pct": 100.0,
                "all_selector_coverage_at_5_pct": 96.0,
                "hit_rate_at_5_pct": 98.0,
                "mrr": 0.9,
                "latency_ms": {"p95": latency},
            }
            for experiment_id, latency in [
                ("vector_baseline", 24.0),
                ("vector_no_overlap", 21.0),
            ]
        }
        shared_signature = "same-treatment"
        selection = selection_analysis(
            summaries,
            {"vector_no_overlap": {"regressed_cases_at_5": []}},
            baseline_id="vector_baseline",
            treatment_metadata={
                "vector_baseline": {
                    "chunk_content_sha256": "same-chunks",
                    "treatment_sha256": shared_signature,
                },
                "vector_no_overlap": {
                    "chunk_content_sha256": "same-chunks",
                    "treatment_sha256": shared_signature,
                },
            },
        )

        self.assertEqual(selection["quality_order"][0], "vector_baseline")
        self.assertEqual(selection["generation_gate_candidates"], ["vector_baseline"])
        self.assertTrue(summaries["vector_no_overlap"]["equivalent_to_baseline"])


class RankingTests(unittest.TestCase):
    def test_treatment_signature_changes_when_governance_filter_changes(self):
        experiment = {
            "strategy": "vector",
            "filter_current_approved": True,
        }
        filtered = treatment_sha256(
            experiment,
            chunk_sha256="chunks",
            candidate_pool=20,
            rank_constant=60,
        )
        experiment["filter_current_approved"] = False
        unfiltered = treatment_sha256(
            experiment,
            chunk_sha256="chunks",
            candidate_pool=20,
            rank_constant=60,
        )

        self.assertNotEqual(filtered, unfiltered)

    def test_rrf_combines_rankings_without_duplicate_documents(self):
        ranked = reciprocal_rank_fusion(
            [["A", "B", "C", "A"], ["B", "D", "A"]],
            top_k=4,
            rank_constant=60,
        )

        self.assertEqual([item.document_id for item in ranked], ["B", "A", "D", "C"])

    def test_reranker_never_introduces_a_non_vector_candidate(self):
        ranked = rerank_vector_candidates(
            ["A", "B", "C"],
            ["D", "B", "A"],
            top_k=3,
            vector_weight=0.65,
        )

        self.assertEqual({item.document_id for item in ranked}, {"A", "B", "C"})
        self.assertNotIn("D", [item.document_id for item in ranked])


class MetricTests(unittest.TestCase):
    def test_selector_coverage_catches_a_partial_cross_family_result(self):
        documents = {
            "A": document("A", family="campaigns", topic="campaign suppression"),
            "B": document("B", family="consent", topic="suppression requirements"),
        }
        case = {
            "case_id": "cross_family_01",
            "category": "cross_family",
            "query": "suppression query",
            "relevant_document_ids": ["A", "B"],
            "relevance_selectors": [
                {"family": "campaigns", "topic": "campaign suppression"},
                {"family": "consent", "topic": "suppression requirements"},
            ],
        }

        partial = score_case(
            case,
            ["A"],
            documents,
            ranks=[1],
            latency_ms=1.0,
        )
        complete = score_case(
            case,
            ["A", "B"],
            documents,
            ranks=[1, 3],
            latency_ms=1.0,
        )

        self.assertTrue(partial["hit_at_1"])
        self.assertFalse(partial["all_selectors_at_1"])
        self.assertEqual(partial["selector_recall_at_1"], 0.5)
        self.assertTrue(complete["all_selectors_at_3"])


class VectorTableTests(unittest.TestCase):
    def test_default_store_keeps_commit07_table_names(self):
        store = PgVectorStore()

        self.assertEqual(store.table_name, "knowledge_chunks")
        self.assertEqual(store.metadata_table_name, "knowledge_index_metadata")

    def test_experiment_tables_receive_isolated_metadata_tables(self):
        store = PgVectorStore(table_name="commit08_chunks_220_40")

        self.assertEqual(store.table_name, "commit08_chunks_220_40")
        self.assertEqual(
            store.metadata_table_name,
            "commit08_chunks_220_40_metadata",
        )

    def test_sql_identifier_validation_rejects_interpolation_characters(self):
        self.assertEqual(validate_sql_identifier("safe_table_01"), "safe_table_01")
        with self.assertRaises(ValueError):
            validate_sql_identifier("knowledge_chunks; drop table users")


if __name__ == "__main__":
    unittest.main()
