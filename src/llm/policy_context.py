from __future__ import annotations

import json
import re
from dataclasses import dataclass

from src.retrieval.query_planner import (
    PlannedPolicyQuery,
    PolicyRetrievalResult,
)


MAX_QUOTE_CHARACTERS = 320


@dataclass(frozen=True)
class PolicyQuote:
    quote_id: str
    document_id: str
    chunk_id: str
    family: str
    text: str

    def to_context_dict(self) -> dict[str, str]:
        return {
            "quote_id": self.quote_id,
            "text": self.text,
        }


@dataclass(frozen=True)
class BuiltPolicyContext:
    json_text: str
    included_results: list[PolicyRetrievalResult]
    quotes_by_id: dict[str, PolicyQuote]
    intent_quote_ids: dict[str, list[str]]
    planned_queries: list[PlannedPolicyQuery]
    character_count: int

    @property
    def document_ids(self) -> list[str]:
        return [result.document_id for result in self.included_results]


def _bounded_segments(text: str) -> list[str]:
    segments = []
    remaining = text.strip()
    while len(remaining) > MAX_QUOTE_CHARACTERS:
        boundary = remaining.rfind(" ", 0, MAX_QUOTE_CHARACTERS + 1)
        if boundary <= 0:
            boundary = MAX_QUOTE_CHARACTERS
        segments.append(remaining[:boundary].strip())
        remaining = remaining[boundary:].strip()
    if remaining:
        segments.append(remaining)
    return segments


def build_policy_quotes(
    result: PolicyRetrievalResult,
    *,
    start_index: int = 1,
) -> list[PolicyQuote]:
    if start_index < 1:
        raise ValueError("start_index must be positive")

    quote_texts = []
    for line in result.content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", line):
            quote_texts.extend(_bounded_segments(sentence))

    return [
        PolicyQuote(
            quote_id=f"Q{index:03d}",
            document_id=result.document_id,
            chunk_id=result.chunk_id,
            family=result.family,
            text=text,
        )
        for index, text in enumerate(quote_texts, start=start_index)
    ]


def context_row(
    result: PolicyRetrievalResult,
    *,
    quote_start_index: int = 1,
) -> tuple[dict, list[PolicyQuote]]:
    if result.status != "CURRENT" or result.authority != "APPROVED":
        raise ValueError(
            f"Policy context rejected non-authoritative source {result.document_id}"
        )
    quotes = build_policy_quotes(result, start_index=quote_start_index)
    if not quotes:
        raise ValueError(
            f"Policy context found no quotable content in {result.document_id}"
        )
    return {
        "document_id": result.document_id,
        "title": result.title,
        "family": result.family,
        "document_type": result.document_type,
        "status": result.status,
        "authority": result.authority,
        "topic": result.topic,
        "retrieval_score": result.score,
        "retrieval_reasons": result.retrieval_reasons,
        "quotes": [quote.to_context_dict() for quote in quotes],
    }, quotes


def policy_intent_id(index: int) -> str:
    return f"I{index:02d}"


def policy_intent_row(index: int, query: PlannedPolicyQuery) -> dict:
    return {
        "intent_id": policy_intent_id(index),
        "reason": query.reason,
        "required_families": query.expected_families,
        "required_document_ids": query.expected_doc_ids,
    }


def build_policy_context(
    results: list[PolicyRetrievalResult],
    *,
    planned_queries: list[PlannedPolicyQuery] | None = None,
    max_characters: int = 16_000,
) -> BuiltPolicyContext:
    if max_characters <= 2:
        raise ValueError("max_characters is too small for JSON context")

    planned_queries = planned_queries or []
    intent_rows = [
        policy_intent_row(index, query)
        for index, query in enumerate(planned_queries, start=1)
    ]
    included_results = []
    included_quotes: dict[str, PolicyQuote] = {}
    rows = []
    for result in results:
        row, quotes = context_row(
            result,
            quote_start_index=len(included_quotes) + 1,
        )
        candidate_rows = [*rows, row]
        candidate_text = json.dumps(
            {
                "required_policy_intents": intent_rows,
                "sources": candidate_rows,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        if len(candidate_text) > max_characters:
            continue
        rows = candidate_rows
        included_results.append(result)
        included_quotes.update({quote.quote_id: quote for quote in quotes})

    if not rows:
        raise ValueError("No retrieved policy result fits the context budget")

    json_text = json.dumps(
        {
            "required_policy_intents": intent_rows,
            "sources": rows,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    intent_quote_ids = {}
    for index, query in enumerate(planned_queries, start=1):
        matching_quote_ids = [
            quote.quote_id
            for quote in included_quotes.values()
            if (
                quote.document_id in query.expected_doc_ids
                if query.expected_doc_ids
                else quote.family in query.expected_families
            )
        ]
        intent_quote_ids[policy_intent_id(index)] = matching_quote_ids

    return BuiltPolicyContext(
        json_text=json_text,
        included_results=included_results,
        quotes_by_id=included_quotes,
        intent_quote_ids=intent_quote_ids,
        planned_queries=planned_queries,
        character_count=len(json_text),
    )
