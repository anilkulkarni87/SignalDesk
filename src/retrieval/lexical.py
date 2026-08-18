from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from .documents import KnowledgeDocument, load_documents


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "be",
    "before",
    "can",
    "for",
    "from",
    "has",
    "have",
    "how",
    "if",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "should",
    "the",
    "this",
    "to",
    "we",
    "what",
    "when",
    "with",
}

SYNONYMS = {
    "discount": {"discount", "offer", "incentive", "promotion"},
    "offer": {"offer", "discount", "incentive", "promotion"},
    "message": {"message", "messaging", "contact", "campaign"},
    "contact": {"contact", "message", "messaging", "campaign"},
    "escalate": {"escalate", "escalation", "handoff", "support"},
    "support": {"support", "escalation", "handoff", "service"},
    "causal": {"causal", "uplift", "cause", "benefit"},
    "automatic": {"automatic", "automated", "execute", "execution"},
}


@dataclass(frozen=True)
class RetrievalResult:
    document_id: str
    title: str
    family: str
    status: str
    authority: str
    score: float
    matched_terms: list[str]
    path: str
    excerpt: str

    def to_dict(self) -> dict:
        return asdict(self)


def tokenize(text: str) -> list[str]:
    normalized = text.lower().replace("_", " ")
    return [
        token
        for token in re.findall(r"[a-z0-9]+", normalized)
        if token not in STOPWORDS and len(token) > 1
    ]


def expand_query_terms(tokens: list[str]) -> set[str]:
    expanded = set(tokens)
    for token in tokens:
        expanded.update(SYNONYMS.get(token, set()))
    return expanded


def document_frequency(documents: list[KnowledgeDocument]) -> Counter:
    df = Counter()
    for doc in documents:
        df.update(set(tokenize(doc.searchable_text)))
    return df


def score_document(
    doc: KnowledgeDocument,
    query_terms: set[str],
    df: Counter,
    document_count: int,
    doc_tokens: list[str] | None = None,
) -> tuple[float, list[str]]:
    doc_tokens = doc_tokens or tokenize(doc.searchable_text)
    counts = Counter(doc_tokens)
    title_terms = set(tokenize(doc.title))
    body_terms = set(doc_tokens)
    matched = sorted(query_terms & body_terms)

    score = 0.0
    for term in matched:
        idf = math.log((document_count + 1) / (1 + df[term])) + 1
        score += counts[term] * idf
        if term in title_terms:
            score += 2.0

    if doc.status == "CURRENT":
        score += 0.5
    if doc.authority == "APPROVED":
        score += 0.5

    return round(score, 4), matched


def excerpt_for(doc: KnowledgeDocument, matched_terms: list[str]) -> str:
    paragraphs = []
    for paragraph in doc.body.split("\n\n"):
        lines = [
            line.strip()
            for line in paragraph.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        cleaned = " ".join(lines)
        if cleaned:
            paragraphs.append(cleaned)

    for term in matched_terms:
        for paragraph in paragraphs:
            if term.lower() in paragraph.lower():
                return paragraph[:500]
    return paragraphs[0][:500] if paragraphs else ""


class LexicalIndex:
    def __init__(self, documents: list[KnowledgeDocument]) -> None:
        if not documents:
            raise ValueError("At least one document is required")
        self.documents = documents
        self._tokens = {
            document.document_id: tokenize(document.searchable_text)
            for document in documents
        }
        self._df = Counter()
        for tokens in self._tokens.values():
            self._df.update(set(tokens))

    @classmethod
    def from_corpus(
        cls,
        corpus_dir: str | Path,
        *,
        statuses: set[str] | None = None,
        authority: set[str] | None = None,
        families: set[str] | None = None,
    ) -> "LexicalIndex":
        documents = load_documents(corpus_dir)
        if statuses is not None:
            documents = [doc for doc in documents if doc.status in statuses]
        if authority is not None:
            documents = [doc for doc in documents if doc.authority in authority]
        if families is not None:
            documents = [doc for doc in documents if doc.family in families]
        return cls(documents)

    def search(
        self,
        query: str,
        *,
        top_k: int = 3,
        statuses: set[str] | None = None,
        authority: set[str] | None = None,
        families: set[str] | None = None,
    ) -> list[RetrievalResult]:
        documents = self.documents
        if statuses is not None:
            documents = [doc for doc in documents if doc.status in statuses]
        if authority is not None:
            documents = [doc for doc in documents if doc.authority in authority]
        if families is not None:
            documents = [doc for doc in documents if doc.family in families]

        query_terms = expand_query_terms(tokenize(query))
        if len(documents) == len(self.documents):
            df = self._df
            token_cache = self._tokens
        else:
            df = document_frequency(documents)
            token_cache = {
                document.document_id: tokenize(document.searchable_text)
                for document in documents
            }
        results = []
        for doc in documents:
            score, matched_terms = score_document(
                doc,
                query_terms,
                df,
                len(documents),
                token_cache[doc.document_id],
            )
            if not matched_terms:
                continue
            results.append(RetrievalResult(
                document_id=doc.document_id,
                title=doc.title,
                family=doc.family,
                status=doc.status,
                authority=doc.authority,
                score=score,
                matched_terms=matched_terms,
                path=str(doc.path),
                excerpt=excerpt_for(doc, matched_terms),
            ))

        return sorted(
            results,
            key=lambda result: (-result.score, result.document_id),
        )[:top_k]


def search(
    query: str,
    *,
    corpus_dir: str | Path = "data/generated/knowledge",
    top_k: int = 3,
    statuses: set[str] | None = None,
    authority: set[str] | None = None,
    families: set[str] | None = None,
) -> list[RetrievalResult]:
    return LexicalIndex.from_corpus(corpus_dir).search(
        query,
        top_k=top_k,
        statuses=statuses,
        authority=authority,
        families=families,
    )
