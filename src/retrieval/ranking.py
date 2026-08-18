from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class RankedDocument:
    document_id: str
    score: float


def _unique_ranking(document_ids: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(document_ids))


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]],
    *,
    top_k: int,
    rank_constant: int = 60,
) -> list[RankedDocument]:
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    if rank_constant < 0:
        raise ValueError("rank_constant must be non-negative")

    scores: dict[str, float] = defaultdict(float)
    best_rank: dict[str, int] = {}
    for ranking in rankings:
        for rank, document_id in enumerate(_unique_ranking(ranking), start=1):
            scores[document_id] += 1.0 / (rank_constant + rank)
            best_rank[document_id] = min(best_rank.get(document_id, rank), rank)

    ordered = sorted(
        scores,
        key=lambda document_id: (
            -scores[document_id],
            best_rank[document_id],
            document_id,
        ),
    )
    return [
        RankedDocument(document_id=document_id, score=round(scores[document_id], 8))
        for document_id in ordered[:top_k]
    ]


def rerank_vector_candidates(
    vector_ranking: Sequence[str],
    lexical_ranking: Sequence[str],
    *,
    top_k: int,
    vector_weight: float = 0.65,
) -> list[RankedDocument]:
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    if not 0.0 <= vector_weight <= 1.0:
        raise ValueError("vector_weight must be between 0 and 1")

    vector_ids = _unique_ranking(vector_ranking)
    lexical_rank = {
        document_id: rank
        for rank, document_id in enumerate(_unique_ranking(lexical_ranking), start=1)
    }
    lexical_weight = 1.0 - vector_weight
    scores = {}
    for vector_rank, document_id in enumerate(vector_ids, start=1):
        vector_score = 1.0 / vector_rank
        lexical_score = (
            1.0 / lexical_rank[document_id]
            if document_id in lexical_rank
            else 0.0
        )
        scores[document_id] = (
            vector_weight * vector_score + lexical_weight * lexical_score
        )

    ordered = sorted(
        vector_ids,
        key=lambda document_id: (
            -scores[document_id],
            vector_ids.index(document_id),
            document_id,
        ),
    )
    return [
        RankedDocument(document_id=document_id, score=round(scores[document_id], 8))
        for document_id in ordered[:top_k]
    ]
