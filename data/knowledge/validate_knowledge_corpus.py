#!/usr/bin/env python3
"""
Validate the NovaCart synthetic knowledge corpus.

Checks:
- requested document count
- unique document IDs
- family coverage
- mixture of current/superseded/draft/incomplete docs
- metadata/frontmatter presence
- deliberate knowledge gaps
- minimum content length
- current authoritative policy coverage
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


REQUIRED_FAMILIES = {
    "retention", "offers", "support", "shipping", "refunds",
    "loyalty", "campaigns", "subscriptions", "consent",
}
REQUIRED_STATUSES = {"CURRENT", "SUPERSEDED", "DRAFT", "INCOMPLETE"}


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--input-dir", type=Path, required=True)
    p.add_argument("--report", type=Path, default=None)
    p.add_argument("--min-documents", type=int, default=1000)
    p.add_argument("--min-words", type=int, default=70)
    return p.parse_args()


def parse_frontmatter(text):
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return None, text

    block = text[4:end]
    body = text[end + 5:]
    metadata = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        try:
            metadata[key.strip()] = json.loads(value)
        except Exception:
            metadata[key.strip()] = value
    return metadata, body


def main():
    args = parse_args()
    report_path = args.report or (args.input_dir / "knowledge_validation_report.json")

    docs = [
        p for p in args.input_dir.rglob("*.md")
        if "_truth" not in p.parts
    ]

    ids = set()
    duplicate_ids = 0
    missing_metadata = 0
    short_docs = 0
    families = Counter()
    statuses = Counter()
    types = Counter()
    current_policy_families = set()

    required_metadata = {
        "document_id", "title", "family", "document_type",
        "status", "version", "effective_date", "author_team", "authority",
    }

    for path in docs:
        text = path.read_text(encoding="utf-8")
        metadata, body = parse_frontmatter(text)

        if metadata is None or not required_metadata.issubset(metadata):
            missing_metadata += 1
            continue

        doc_id = metadata["document_id"]
        if doc_id in ids:
            duplicate_ids += 1
        ids.add(doc_id)

        families[metadata["family"]] += 1
        statuses[metadata["status"]] += 1
        types[metadata["document_type"]] += 1

        if (
            metadata["status"] == "CURRENT"
            and metadata["document_type"] == "POLICY"
            and metadata["authority"] == "APPROVED"
        ):
            current_policy_families.add(metadata["family"])

        words = re.findall(r"\b[\w'-]+\b", body)
        if len(words) < args.min_words:
            short_docs += 1

    gaps_path = args.input_dir / "_truth" / "known_knowledge_gaps.json"
    gaps = []
    if gaps_path.exists():
        gaps = json.loads(gaps_path.read_text(encoding="utf-8"))

    tests = {
        "document_count": {
            "actual": len(docs),
            "minimum": args.min_documents,
            "passed": len(docs) >= args.min_documents,
        },
        "unique_document_ids": {
            "duplicates": duplicate_ids,
            "passed": duplicate_ids == 0,
        },
        "metadata_complete": {
            "documents_missing_required_metadata": missing_metadata,
            "passed": missing_metadata == 0,
        },
        "minimum_content_length": {
            "short_documents": short_docs,
            "minimum_words": args.min_words,
            "passed": short_docs == 0,
        },
        "family_coverage": {
            "missing_families": sorted(REQUIRED_FAMILIES - set(families)),
            "passed": REQUIRED_FAMILIES.issubset(families),
        },
        "status_mixture": {
            "missing_statuses": sorted(REQUIRED_STATUSES - set(statuses)),
            "passed": REQUIRED_STATUSES.issubset(statuses),
        },
        "current_authoritative_policy_coverage": {
            "families_with_current_approved_policy": sorted(current_policy_families),
            "missing_families": sorted(REQUIRED_FAMILIES - current_policy_families),
            "passed": REQUIRED_FAMILIES.issubset(current_policy_families),
        },
        "known_knowledge_gaps": {
            "count": len(gaps),
            "passed": len(gaps) >= 3,
        },
    }

    report = {
        "documents": len(docs),
        "family_counts": dict(families),
        "status_counts": dict(statuses),
        "document_type_counts": dict(types),
        "tests": tests,
        "passed": all(v["passed"] for v in tests.values()),
    }

    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
