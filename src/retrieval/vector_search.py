#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json

from .embeddings import DEFAULT_EMBEDDING_MODEL, OpenAIEmbedder
from .vector_store import PgVectorStore


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--dsn")
    parser.add_argument("--model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--dimensions", type=int)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--include-non-authoritative", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    embedder = OpenAIEmbedder(model=args.model, dimensions=args.dimensions)
    embedding = embedder.embed([args.query]).vectors[0]
    store = PgVectorStore(args.dsn)
    results = store.search(
        embedding,
        top_k=args.top_k,
        statuses=None if args.include_non_authoritative else {"CURRENT"},
        authorities=None if args.include_non_authoritative else {"APPROVED"},
    )
    print(json.dumps([result.to_dict() for result in results], indent=2))


if __name__ == "__main__":
    main()
