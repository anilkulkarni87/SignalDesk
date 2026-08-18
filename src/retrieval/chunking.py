from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .documents import KnowledgeDocument


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    document_id: str
    title: str
    family: str
    document_type: str
    status: str
    authority: str
    topic: str
    section_names: list[str]
    position: int
    content: str
    source_path: str

    @property
    def embedding_text(self) -> str:
        context = [
            f"Document title: {self.title}",
            f"Knowledge family: {self.family}",
            f"Document topic: {self.topic}",
            f"Document type: {self.document_type}",
            f"Sections: {', '.join(self.section_names)}",
        ]
        return "\n".join(context) + "\n\n" + self.content

    def to_dict(self) -> dict:
        return asdict(self)


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def split_markdown_sections(body: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    heading = "Document"
    lines: list[str] = []

    for line in body.splitlines():
        match = HEADING_RE.match(line)
        if match:
            content = "\n".join(lines).strip()
            if content:
                sections.append((heading, content))
            heading = match.group(2).strip()
            lines = []
        else:
            lines.append(line)

    content = "\n".join(lines).strip()
    if content:
        sections.append((heading, content))
    return sections


def split_long_section(
    heading: str,
    content: str,
    *,
    max_words: int,
    overlap_words: int,
) -> list[tuple[list[str], str]]:
    words = content.split()
    prefix = f"## {heading}"
    content_budget = max_words - word_count(prefix)
    if content_budget <= 0:
        raise ValueError(f"Heading is too long for max_words={max_words}: {heading}")
    if len(words) <= content_budget:
        return [([heading], f"{prefix}\n{content}")]

    if overlap_words >= content_budget:
        raise ValueError("overlap_words leaves no room for section content")
    step = content_budget - overlap_words
    parts = []
    for start in range(0, len(words), step):
        part = words[start:start + content_budget]
        if not part:
            break
        parts.append(([heading], f"{prefix}\n{' '.join(part)}"))
        if start + content_budget >= len(words):
            break
    return parts


def chunk_document(
    document: KnowledgeDocument,
    *,
    max_words: int = 220,
    overlap_words: int = 40,
) -> list[KnowledgeChunk]:
    if max_words <= 0:
        raise ValueError("max_words must be positive")
    if overlap_words < 0 or overlap_words >= max_words:
        raise ValueError("overlap_words must be between 0 and max_words - 1")

    units: list[tuple[list[str], str]] = []
    for heading, content in split_markdown_sections(document.body):
        units.extend(split_long_section(
            heading,
            content,
            max_words=max_words,
            overlap_words=overlap_words,
        ))

    packed: list[tuple[list[str], str]] = []
    current_headings: list[str] = []
    current_parts: list[str] = []
    current_words = 0

    for headings, text in units:
        unit_words = word_count(text)
        if current_parts and current_words + unit_words > max_words:
            packed.append((current_headings, "\n\n".join(current_parts)))
            current_headings = []
            current_parts = []
            current_words = 0
        current_headings.extend(headings)
        current_parts.append(text)
        current_words += unit_words

    if current_parts:
        packed.append((current_headings, "\n\n".join(current_parts)))

    topic = str(document.metadata.get("topic", ""))
    return [
        KnowledgeChunk(
            chunk_id=f"{document.document_id}::chunk-{position:03d}",
            document_id=document.document_id,
            title=document.title,
            family=document.family,
            document_type=document.document_type,
            status=document.status,
            authority=document.authority,
            topic=topic,
            section_names=headings,
            position=position,
            content=content,
            source_path=str(document.path),
        )
        for position, (headings, content) in enumerate(packed)
    ]


def chunk_documents(
    documents: list[KnowledgeDocument],
    *,
    max_words: int = 220,
    overlap_words: int = 40,
) -> list[KnowledgeChunk]:
    chunks = []
    for document in documents:
        chunks.extend(chunk_document(
            document,
            max_words=max_words,
            overlap_words=overlap_words,
        ))
    return chunks
