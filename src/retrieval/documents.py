from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class KnowledgeDocument:
    document_id: str
    title: str
    family: str
    document_type: str
    status: str
    version: str
    effective_date: str
    authority: str
    path: Path
    body: str
    metadata: dict[str, Any]

    @property
    def searchable_text(self) -> str:
        return "\n".join([
            self.document_id,
            self.title,
            self.family,
            self.document_type,
            self.status,
            self.authority,
            self.body,
        ])


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        raise ValueError("Document is missing frontmatter")

    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValueError("Document frontmatter is not closed")

    metadata: dict[str, Any] = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        raw_value = raw_value.strip()
        try:
            value = json.loads(raw_value)
        except json.JSONDecodeError:
            value = raw_value
        metadata[key.strip()] = value

    return metadata, text[end + 5:].strip()


def load_documents(corpus_dir: str | Path) -> list[KnowledgeDocument]:
    root = Path(corpus_dir)
    documents = []
    required = {
        "document_id",
        "title",
        "family",
        "document_type",
        "status",
        "version",
        "effective_date",
        "authority",
    }

    for path in sorted(root.rglob("*.md")):
        if "_truth" in path.parts:
            continue
        metadata, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        missing = required - set(metadata)
        if missing:
            raise ValueError(f"{path} is missing metadata: {sorted(missing)}")

        documents.append(KnowledgeDocument(
            document_id=str(metadata["document_id"]),
            title=str(metadata["title"]),
            family=str(metadata["family"]),
            document_type=str(metadata["document_type"]),
            status=str(metadata["status"]),
            version=str(metadata["version"]),
            effective_date=str(metadata["effective_date"]),
            authority=str(metadata["authority"]),
            path=path,
            body=body,
            metadata=metadata,
        ))

    gaps_path = root / "_truth" / "known_knowledge_gaps.json"
    if gaps_path.exists():
        gaps = json.loads(gaps_path.read_text(encoding="utf-8"))
        for gap in gaps:
            gap_id = str(gap["gap_id"])
            documents.append(KnowledgeDocument(
                document_id=gap_id,
                title=str(gap["topic"]).title(),
                family="governance",
                document_type="KNOWN_GAP",
                status="CURRENT",
                version="1.0",
                effective_date="2026-08-01",
                authority="APPROVED",
                path=gaps_path,
                body=(
                    f"Known gap: {gap['topic']}\n\n"
                    f"Reason: {gap['reason']}\n\n"
                    f"Expected behavior: {gap['expected_behavior']}"
                ),
                metadata=gap,
            ))

    if not documents:
        raise ValueError(f"No Markdown documents found in {root}")

    return documents
