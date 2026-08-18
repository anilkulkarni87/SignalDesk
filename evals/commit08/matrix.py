#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from evals.commit08.metrics import (
    chunk_content_sha256,
    compare_to_baseline,
    score_case,
    summarize_experiment,
    treatment_sha256,
    validate_frozen_inputs,
)
from src.retrieval.chunking import chunk_documents
from src.retrieval.documents import KnowledgeDocument, load_documents
from src.retrieval.embeddings import OpenAIEmbedder
from src.retrieval.lexical import LexicalIndex
from src.retrieval.ranking import reciprocal_rank_fusion, rerank_vector_candidates
from src.retrieval.vector_store import PgVectorStore


VECTOR_STRATEGIES = {"vector", "hybrid_rrf", "vector_lexical_rerank"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path("evals/commit08/experiment_contract.json"),
    )
    parser.add_argument(
        "--stage",
        choices=("validate", "build", "benchmark", "all"),
        default="validate",
    )
    parser.add_argument(
        "--experiment",
        action="append",
        help="Run only this experiment ID; may be supplied more than once.",
    )
    parser.add_argument("--dsn")
    parser.add_argument("--embedding-batch-size", type=int, default=64)
    parser.add_argument("--database-batch-size", type=int, default=200)
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("evals/commit08/reports/retrieval_experiment_matrix.json"),
    )
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def validate_contract(contract: dict[str, Any]) -> None:
    required_str = {
        "experiment_version",
        "cases_file",
        "cases_sha256",
        "corpus_dir",
        "corpus_sha256",
        "embedding_model",
        "baseline_experiment_id",
    }
    missing = required_str - set(contract)
    if missing:
        raise ValueError(f"Experiment contract is missing fields: {sorted(missing)}")
    if not contract.get("experiments"):
        raise ValueError("Experiment contract must define experiments")
    experiment_ids = [item["experiment_id"] for item in contract["experiments"]]
    if len(experiment_ids) != len(set(experiment_ids)):
        raise ValueError("Experiment IDs must be unique")
    if contract["baseline_experiment_id"] not in experiment_ids:
        raise ValueError("Baseline experiment ID is not defined")
    ranks = contract.get("ranks", [])
    if not ranks or ranks != sorted(set(ranks)) or any(rank <= 0 for rank in ranks):
        raise ValueError("Ranks must be unique positive integers in ascending order")
    if contract.get("candidate_pool", 0) < max(ranks):
        raise ValueError("candidate_pool must be at least the largest evaluation rank")

    table_specs: dict[str, tuple[int, int]] = {}
    for experiment in contract["experiments"]:
        strategy = experiment["strategy"]
        if strategy not in {"lexical", *VECTOR_STRATEGIES}:
            raise ValueError(f"Unsupported strategy: {strategy}")
        if strategy not in VECTOR_STRATEGIES:
            continue
        table = experiment["index_table"]
        spec = (experiment["max_words"], experiment["overlap_words"])
        if table in table_specs and table_specs[table] != spec:
            raise ValueError(f"Index table {table} has conflicting chunk settings")
        table_specs[table] = spec


def select_experiments(
    contract: dict[str, Any],
    requested_ids: list[str] | None,
) -> list[dict[str, Any]]:
    experiments = contract["experiments"]
    if not requested_ids:
        return experiments
    requested = set(requested_ids)
    known = {experiment["experiment_id"] for experiment in experiments}
    unknown = requested - known
    if unknown:
        raise ValueError(f"Unknown experiment IDs: {sorted(unknown)}")
    return [
        experiment
        for experiment in experiments
        if experiment["experiment_id"] in requested
    ]


def index_specs(experiments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_table: dict[str, dict[str, Any]] = {}
    for experiment in experiments:
        if experiment["strategy"] not in VECTOR_STRATEGIES:
            continue
        table = experiment["index_table"]
        by_table.setdefault(table, {
            "index_table": table,
            "max_words": experiment["max_words"],
            "overlap_words": experiment["overlap_words"],
        })
    return [by_table[table] for table in sorted(by_table)]


def build_treatment_metadata(
    contract: dict[str, Any],
    experiments: list[dict[str, Any]],
    documents: list[KnowledgeDocument],
) -> dict[str, dict[str, str | None]]:
    chunk_sha_by_table = {}
    for spec in index_specs(experiments):
        chunks = chunk_documents(
            documents,
            max_words=spec["max_words"],
            overlap_words=spec["overlap_words"],
        )
        chunk_sha_by_table[spec["index_table"]] = chunk_content_sha256(chunks)

    treatment_metadata = {}
    for experiment in experiments:
        chunk_sha = (
            chunk_sha_by_table[experiment["index_table"]]
            if experiment["strategy"] in VECTOR_STRATEGIES
            else None
        )
        treatment_metadata[experiment["experiment_id"]] = {
            "chunk_content_sha256": chunk_sha,
            "treatment_sha256": treatment_sha256(
                experiment,
                chunk_sha256=chunk_sha,
                candidate_pool=contract["candidate_pool"],
                rank_constant=contract["rrf_rank_constant"],
            ),
        }
    return treatment_metadata


def equivalent_treatment_groups(
    treatment_metadata: dict[str, dict[str, str | None]],
) -> list[list[str]]:
    by_signature: dict[str, list[str]] = {}
    for experiment_id, metadata in treatment_metadata.items():
        signature = str(metadata["treatment_sha256"])
        by_signature.setdefault(signature, []).append(experiment_id)
    return [
        sorted(experiment_ids)
        for experiment_ids in by_signature.values()
        if len(experiment_ids) > 1
    ]


def selection_analysis(
    summaries: dict[str, dict[str, Any]],
    comparisons: dict[str, dict[str, Any]],
    *,
    baseline_id: str,
    treatment_metadata: dict[str, dict[str, str | None]],
) -> dict[str, Any]:
    for experiment_id, metadata in treatment_metadata.items():
        if experiment_id in summaries:
            summaries[experiment_id].update(metadata)

    baseline_treatment = summaries.get(baseline_id, {}).get("treatment_sha256")
    for experiment_id, summary in summaries.items():
        summary["equivalent_to_baseline"] = (
            experiment_id != baseline_id
            and summary.get("treatment_sha256") == baseline_treatment
        )

    quality_order = sorted(
        summaries,
        key=lambda experiment_id: (
            summaries[experiment_id]["equivalent_to_baseline"],
            -summaries[experiment_id]["current_approved_result_rate_at_5_pct"],
            -summaries[experiment_id]["all_selector_coverage_at_5_pct"],
            -summaries[experiment_id]["hit_rate_at_5_pct"],
            -summaries[experiment_id]["mrr"],
            summaries[experiment_id]["latency_ms"]["p95"],
            experiment_id,
        ),
    )
    baseline_coverage = summaries.get(baseline_id, {}).get(
        "all_selector_coverage_at_5_pct",
        0.0,
    )
    generation_gate_candidates = []
    for experiment_id in quality_order:
        summary = summaries[experiment_id]
        comparison = comparisons.get(experiment_id)
        has_no_regressions = (
            experiment_id == baseline_id
            or comparison is None
            or not comparison["regressed_cases_at_5"]
        )
        if all([
            summary["filter_current_approved"],
            summary["current_approved_result_rate_at_5_pct"] == 100.0,
            summary["all_selector_coverage_at_5_pct"] >= baseline_coverage,
            has_no_regressions,
            not summary["equivalent_to_baseline"],
        ]):
            generation_gate_candidates.append(experiment_id)

    return {
        "quality_order": quality_order,
        "generation_gate_candidates": generation_gate_candidates,
        "equivalent_treatment_groups": equivalent_treatment_groups(
            treatment_metadata
        ),
    }


def expected_index_metadata(
    contract: dict[str, Any],
    spec: dict[str, Any],
) -> dict[str, Any]:
    return {
        "experiment_version": contract["experiment_version"],
        "corpus_sha256": contract["corpus_sha256"],
        "embedding_model": contract["embedding_model"],
        "embedding_dimensions": contract["embedding_dimensions"],
        "max_words": spec["max_words"],
        "overlap_words": spec["overlap_words"],
    }


def metadata_matches(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(actual.get(key) == value for key, value in expected.items())


def build_indexes(
    contract: dict[str, Any],
    experiments: list[dict[str, Any]],
    *,
    dsn: str | None,
    embedding_batch_size: int,
    database_batch_size: int,
    rebuild: bool,
) -> list[dict[str, Any]]:
    documents = load_documents(contract["corpus_dir"])
    reports = []
    for spec in index_specs(experiments):
        store = PgVectorStore(dsn, table_name=spec["index_table"])
        expected = expected_index_metadata(contract, spec)
        actual = store.get_metadata()
        if not rebuild and metadata_matches(actual, expected):
            reports.append({
                "index_table": spec["index_table"],
                "status": "reused",
                **actual,
            })
            continue

        started = perf_counter()
        chunks = chunk_documents(
            documents,
            max_words=spec["max_words"],
            overlap_words=spec["overlap_words"],
        )
        embedder = OpenAIEmbedder(
            model=contract["embedding_model"],
            dimensions=contract["embedding_dimensions"],
            batch_size=embedding_batch_size,
        )
        embedding_started = perf_counter()
        embedding_run = embedder.embed([chunk.embedding_text for chunk in chunks])
        embedding_latency_ms = (perf_counter() - embedding_started) * 1000

        store.ensure_schema(embedding_run.dimensions, recreate=True)
        inserted = store.upsert_chunks(
            zip(chunks, embedding_run.vectors),
            batch_size=database_batch_size,
        )
        store.create_hnsw_index()
        metadata = {
            **expected,
            "corpus_dir": contract["corpus_dir"],
            "document_count": len(documents),
            "chunk_count": len(chunks),
            "built_at": datetime.now(UTC).isoformat(),
        }
        store.set_metadata(metadata)
        reports.append({
            "index_table": spec["index_table"],
            "status": "built",
            **metadata,
            "inserted_chunks": inserted,
            "embedding_input_tokens": embedding_run.input_tokens,
            "embedding_latency_ms": round(embedding_latency_ms, 3),
            "total_build_latency_ms": round((perf_counter() - started) * 1000, 3),
        })
    return reports


def require_indexes(
    contract: dict[str, Any],
    experiments: list[dict[str, Any]],
    dsn: str | None,
) -> dict[str, dict[str, Any]]:
    metadata_by_table = {}
    for spec in index_specs(experiments):
        store = PgVectorStore(dsn, table_name=spec["index_table"])
        actual = store.get_metadata()
        expected = expected_index_metadata(contract, spec)
        if not metadata_matches(actual, expected):
            raise RuntimeError(
                f"Index {spec['index_table']} is missing or stale; run --stage build first"
            )
        metadata_by_table[spec["index_table"]] = actual
    return metadata_by_table


def _filters(experiment: dict[str, Any]) -> tuple[set[str] | None, set[str] | None]:
    if experiment["filter_current_approved"]:
        return {"CURRENT"}, {"APPROVED"}
    return None, None


def retrieve_ids(
    experiment: dict[str, Any],
    case: dict[str, Any],
    *,
    query_vector: list[float] | None,
    dsn: str | None,
    lexical_filtered: LexicalIndex,
    lexical_unfiltered: LexicalIndex,
    candidate_pool: int,
    rank_constant: int,
) -> tuple[list[str], float]:
    statuses, authorities = _filters(experiment)
    lexical_index = lexical_filtered if statuses else lexical_unfiltered
    started = perf_counter()
    strategy = experiment["strategy"]

    if strategy == "lexical":
        results = lexical_index.search(case["query"], top_k=candidate_pool)
        return [result.document_id for result in results], (perf_counter() - started) * 1000

    if query_vector is None:
        raise ValueError(f"{strategy} requires a query vector")
    store = PgVectorStore(dsn, table_name=experiment["index_table"])
    vector_results = store.search(
        query_vector,
        top_k=candidate_pool,
        statuses=statuses,
        authorities=authorities,
    )
    vector_ids = [result.document_id for result in vector_results]
    if strategy == "vector":
        return vector_ids, (perf_counter() - started) * 1000

    lexical_results = lexical_index.search(case["query"], top_k=candidate_pool)
    lexical_ids = [result.document_id for result in lexical_results]
    if strategy == "hybrid_rrf":
        ranked = reciprocal_rank_fusion(
            [vector_ids, lexical_ids],
            top_k=candidate_pool,
            rank_constant=rank_constant,
        )
    elif strategy == "vector_lexical_rerank":
        ranked = rerank_vector_candidates(
            vector_ids,
            lexical_ids,
            top_k=candidate_pool,
            vector_weight=experiment.get("vector_weight", 0.65),
        )
    else:
        raise ValueError(f"Unsupported strategy: {strategy}")
    return [result.document_id for result in ranked], (perf_counter() - started) * 1000


def benchmark(
    contract: dict[str, Any],
    experiments: list[dict[str, Any]],
    *,
    dsn: str | None,
    embedding_batch_size: int,
) -> dict[str, Any]:
    cases = read_jsonl(contract["cases_file"])
    if len(cases) != 50:
        raise ValueError(f"Expected 50 frozen retrieval cases, found {len(cases)}")
    documents = load_documents(contract["corpus_dir"])
    documents_by_id = {document.document_id: document for document in documents}
    if len(documents_by_id) != len(documents):
        raise ValueError("Knowledge corpus contains duplicate document IDs")
    treatment_metadata = build_treatment_metadata(
        contract,
        experiments,
        documents,
    )

    metadata_by_table = require_indexes(contract, experiments, dsn)
    lexical_filtered = LexicalIndex([
        document
        for document in documents
        if document.status == "CURRENT" and document.authority == "APPROVED"
    ])
    lexical_unfiltered = LexicalIndex(documents)

    needs_vectors = any(
        experiment["strategy"] in VECTOR_STRATEGIES
        for experiment in experiments
    )
    query_vectors: dict[str, list[float]] = {}
    query_embedding_report = None
    average_embedding_latency_ms = 0.0
    if needs_vectors:
        embedder = OpenAIEmbedder(
            model=contract["embedding_model"],
            dimensions=contract["embedding_dimensions"],
            batch_size=embedding_batch_size,
        )
        started = perf_counter()
        embedding_run = embedder.embed([case["query"] for case in cases])
        embedding_latency_ms = (perf_counter() - started) * 1000
        average_embedding_latency_ms = embedding_latency_ms / len(cases)
        query_vectors = {
            case["case_id"]: vector
            for case, vector in zip(cases, embedding_run.vectors)
        }
        query_embedding_report = {
            "model": embedding_run.model,
            "dimensions": embedding_run.dimensions,
            "input_count": embedding_run.input_count,
            "input_tokens": embedding_run.input_tokens,
            "batch_latency_ms": round(embedding_latency_ms, 3),
            "amortized_latency_per_case_ms": round(average_embedding_latency_ms, 3),
        }

    summaries = {}
    for experiment in experiments:
        case_reports = []
        for case in cases:
            query_vector = query_vectors.get(case["case_id"])
            retrieved_ids, search_latency_ms = retrieve_ids(
                experiment,
                case,
                query_vector=query_vector,
                dsn=dsn,
                lexical_filtered=lexical_filtered,
                lexical_unfiltered=lexical_unfiltered,
                candidate_pool=contract["candidate_pool"],
                rank_constant=contract["rrf_rank_constant"],
            )
            embedding_share = (
                average_embedding_latency_ms
                if experiment["strategy"] in VECTOR_STRATEGIES
                else 0.0
            )
            case_reports.append(score_case(
                case,
                retrieved_ids,
                documents_by_id,
                ranks=contract["ranks"],
                latency_ms=search_latency_ms + embedding_share,
            ))
        index_metadata = (
            metadata_by_table[experiment["index_table"]]
            if experiment["strategy"] in VECTOR_STRATEGIES
            else None
        )
        summaries[experiment["experiment_id"]] = summarize_experiment(
            experiment,
            case_reports,
            ranks=contract["ranks"],
            index_metadata=index_metadata,
        )

    baseline_id = contract["baseline_experiment_id"]
    comparisons = {}
    if baseline_id in summaries:
        baseline = summaries[baseline_id]
        comparisons = {
            experiment_id: compare_to_baseline(baseline, summary)
            for experiment_id, summary in summaries.items()
            if experiment_id != baseline_id
        }

    selection = selection_analysis(
        summaries,
        comparisons,
        baseline_id=baseline_id,
        treatment_metadata=treatment_metadata,
    )
    return {
        "experiment_version": contract["experiment_version"],
        "cases_file": contract["cases_file"],
        "cases_sha256": contract["cases_sha256"],
        "corpus_dir": contract["corpus_dir"],
        "corpus_sha256": contract["corpus_sha256"],
        "cases": len(cases),
        "query_embedding": query_embedding_report,
        "selection_rule": (
            "Require 100% current-approved results, no selector-coverage regression, "
            "and selector coverage@5 at least as high as the baseline. Exclude "
            "behaviorally equivalent treatments. Then order by "
            "selector coverage@5, hit rate@5, MRR, and p95 latency. A listed candidate "
            "still requires the separate Commit 07 generation gate before adoption."
        ),
        **selection,
        "experiments": summaries,
        "comparisons_to_baseline": comparisons,
    }


def console_view(report: dict[str, Any]) -> dict[str, Any]:
    experiments = {}
    for experiment_id, summary in report.get("experiments", {}).items():
        experiments[experiment_id] = {
            key: value
            for key, value in summary.items()
            if key not in {"case_reports", "metric_definitions", "by_category"}
        }
    return {
        key: value
        for key, value in report.items()
        if key not in {"experiments"}
    } | {"experiments": experiments}


def main() -> None:
    args = parse_args()
    contract = read_json(args.contract)
    validate_contract(contract)
    validate_frozen_inputs(contract)
    experiments = select_experiments(contract, args.experiment)

    documents = load_documents(contract["corpus_dir"])
    treatment_metadata = build_treatment_metadata(contract, experiments, documents)

    plan = {
        "experiment_version": contract["experiment_version"],
        "stage": args.stage,
        "cases": len(read_jsonl(contract["cases_file"])),
        "experiments": [item["experiment_id"] for item in experiments],
        "indexes": index_specs(experiments),
        "equivalent_treatment_groups": equivalent_treatment_groups(
            treatment_metadata
        ),
        "frozen_input_validation": "passed",
    }
    if args.stage == "validate":
        print(json.dumps(plan, indent=2))
        return

    output: dict[str, Any] = {"plan": plan}
    if args.stage in {"build", "all"}:
        output["index_builds"] = build_indexes(
            contract,
            experiments,
            dsn=args.dsn,
            embedding_batch_size=args.embedding_batch_size,
            database_batch_size=args.database_batch_size,
            rebuild=args.rebuild,
        )
    if args.stage in {"benchmark", "all"}:
        output.update(benchmark(
            contract,
            experiments,
            dsn=args.dsn,
            embedding_batch_size=args.embedding_batch_size,
        ))

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(console_view(output), indent=2))


if __name__ == "__main__":
    main()
