#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from .chunking import chunk_documents
from .documents import load_documents
from .embeddings import DEFAULT_EMBEDDING_MODEL, OpenAIEmbedder
from .vector_store import PgVectorStore


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-dir", default="data/generated/knowledge")
    parser.add_argument("--dsn")
    parser.add_argument("--model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--dimensions", type=int)
    parser.add_argument("--embedding-batch-size", type=int, default=64)
    parser.add_argument("--database-batch-size", type=int, default=200)
    parser.add_argument("--max-words", type=int, default=220)
    parser.add_argument("--overlap-words", type=int, default=40)
    parser.add_argument("--recreate", action="store_true")
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("evals/commit06/reports/vector_index_manifest.json"),
    )
    return parser.parse_args()


def main():
    args = parse_args()
    started = perf_counter()
    documents = load_documents(args.corpus_dir)
    chunks = chunk_documents(
        documents,
        max_words=args.max_words,
        overlap_words=args.overlap_words,
    )
    store = PgVectorStore(args.dsn)
    store.check_connection()

    embedder = OpenAIEmbedder(
        model=args.model,
        dimensions=args.dimensions,
        batch_size=args.embedding_batch_size,
    )
    embedding_started = perf_counter()
    embedding_run = embedder.embed([chunk.embedding_text for chunk in chunks])
    embedding_ms = round((perf_counter() - embedding_started) * 1000, 2)

    store.ensure_schema(embedding_run.dimensions, recreate=args.recreate)
    inserted = store.upsert_chunks(
        zip(chunks, embedding_run.vectors),
        batch_size=args.database_batch_size,
    )
    store.create_hnsw_index()

    metadata = {
        "embedding_model": embedding_run.model,
        "embedding_dimensions": embedding_run.dimensions,
        "corpus_dir": str(args.corpus_dir),
        "document_count": len(documents),
        "chunk_count": len(chunks),
        "max_words": args.max_words,
        "overlap_words": args.overlap_words,
        "built_at": datetime.now(UTC).isoformat(),
    }
    store.set_metadata(metadata)

    report = {
        **metadata,
        "inserted_chunks": inserted,
        "embedding_input_tokens": embedding_run.input_tokens,
        "embedding_latency_ms": embedding_ms,
        "total_latency_ms": round((perf_counter() - started) * 1000, 2),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
