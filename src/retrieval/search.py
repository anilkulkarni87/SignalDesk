from __future__ import annotations

import argparse
import json

from .lexical import search


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("query")
    p.add_argument("--corpus-dir", default="data/generated/knowledge")
    p.add_argument("--top-k", type=int, default=3)
    p.add_argument(
        "--include-superseded",
        action="store_true",
        help="Include superseded documents for freshness testing.",
    )
    return p.parse_args()


def main():
    args = parse_args()
    statuses = None if args.include_superseded else {"CURRENT"}
    results = search(
        args.query,
        corpus_dir=args.corpus_dir,
        top_k=args.top_k,
        statuses=statuses,
        authority={"APPROVED"},
    )
    print(json.dumps([r.to_dict() for r in results], indent=2))


if __name__ == "__main__":
    main()
