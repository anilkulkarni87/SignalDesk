from __future__ import annotations

import unittest
from pathlib import Path

from evals.commit06.make_retrieval_cases import build_cases
from evals.commit06.retrieval_benchmark import score_case
from src.retrieval.chunking import chunk_document, word_count
from src.retrieval.documents import KnowledgeDocument, load_documents
from src.retrieval.vector_store import vector_literal


class ChunkingTests(unittest.TestCase):
    def test_chunks_preserve_metadata_and_respect_max_words(self):
        document = KnowledgeDocument(
            document_id="KB-TEST",
            title="Test Policy",
            family="support",
            document_type="POLICY",
            status="CURRENT",
            version="1.0",
            effective_date="2026-08-01",
            authority="APPROVED",
            path=Path("test.md"),
            body=(
                "# Test Policy\n\n"
                "## Purpose\n" + "purpose " * 60 + "\n\n"
                "## Core guidance\n" + "guidance " * 160
            ),
            metadata={"topic": "test topic"},
        )

        chunks = chunk_document(document, max_words=80, overlap_words=10)

        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(all(chunk.document_id == "KB-TEST" for chunk in chunks))
        self.assertTrue(all(chunk.topic == "test topic" for chunk in chunks))
        self.assertTrue(all(word_count(chunk.content) <= 80 for chunk in chunks))
        self.assertIn("Document topic: test topic", chunks[0].embedding_text)


class CaseGenerationTests(unittest.TestCase):
    def test_generated_corpus_produces_fifty_grounded_cases(self):
        cases = build_cases(load_documents("data/generated/knowledge"))

        self.assertEqual(len(cases), 50)
        self.assertEqual(len({case["case_id"] for case in cases}), 50)
        self.assertTrue(all(case["relevant_document_ids"] for case in cases))


class MetricTests(unittest.TestCase):
    def test_recall_and_reciprocal_rank_use_first_relevant_document(self):
        case = {
            "case_id": "metric_01",
            "category": "test",
            "query": "test query",
            "relevant_document_ids": ["B", "C"],
        }

        report = score_case(case, ["A", "B", "D", "E", "F"], 1.5)

        self.assertFalse(report["recall_at_1"])
        self.assertTrue(report["recall_at_3"])
        self.assertEqual(report["first_relevant_rank"], 2)
        self.assertEqual(report["reciprocal_rank"], 0.5)


class VectorSerializationTests(unittest.TestCase):
    def test_vector_literal_rejects_empty_and_non_finite_values(self):
        self.assertEqual(vector_literal([1, 0.25, -2]), "[1,0.25,-2]")
        with self.assertRaises(ValueError):
            vector_literal([])
        with self.assertRaises(ValueError):
            vector_literal([float("nan")])


if __name__ == "__main__":
    unittest.main()
