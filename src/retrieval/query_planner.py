from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any

from .embeddings import OpenAIEmbedder
from .vector_store import PgVectorStore, VectorSearchResult


@dataclass(frozen=True)
class PlannedPolicyQuery:
    reason: str
    query: str
    expected_families: list[str]
    expected_doc_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PolicyRetrievalResult:
    chunk_id: str
    document_id: str
    title: str
    family: str
    document_type: str
    status: str
    authority: str
    topic: str
    score: float
    best_query_rank: int
    content: str
    source_path: str
    matched_queries: list[str]
    retrieval_reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_vector_result(
        cls,
        result: VectorSearchResult,
        planned_query: PlannedPolicyQuery,
        query_rank: int,
    ) -> "PolicyRetrievalResult":
        return cls(
            **asdict(result),
            best_query_rank=query_rank,
            matched_queries=[planned_query.query],
            retrieval_reasons=[planned_query.reason],
        )


def plan_policy_queries(snapshot: dict[str, Any]) -> list[PlannedPolicyQuery]:
    """Choose policy lookups deterministically from Customer 360 facts."""

    queries: list[PlannedPolicyQuery] = []

    purchase_decline = bool(snapshot.get("purchase_decline_flag"))
    engagement_decline = bool(snapshot.get("engagement_decline_flag"))
    support_attention = bool(snapshot.get("support_attention_flag"))
    recent_subscription_cancel = bool(
        snapshot.get("recent_subscription_cancellation_flag")
    )
    email_opted_in = bool(snapshot.get("email_opted_in"))
    sms_opted_in = bool(snapshot.get("sms_opted_in"))
    push_opted_in = bool(snapshot.get("push_opted_in"))

    if support_attention:
        queries.append(PlannedPolicyQuery(
            reason="support_attention_flag is true",
            query="open support case support escalation handoff",
            expected_families=["support"],
            expected_doc_ids=[],
        ))

    if purchase_decline or engagement_decline:
        queries.append(PlannedPolicyQuery(
            reason="decline signals require retention decision guidance",
            query=(
                "retention investigation declining purchase weakening "
                "engagement evidence intervention decision"
            ),
            expected_families=["retention"],
            expected_doc_ids=[],
        ))
        queries.append(PlannedPolicyQuery(
            reason="purchase or engagement decline may require retention guidance",
            query="retention offer eligibility cooling period discount",
            expected_families=["offers"],
            expected_doc_ids=[],
        ))

    if not (email_opted_in and sms_opted_in and push_opted_in):
        queries.append(PlannedPolicyQuery(
            reason="one or more outbound channels are opted out",
            query="customer communication consent email opt out suppression",
            expected_families=["consent"],
            expected_doc_ids=[],
        ))

    if recent_subscription_cancel:
        queries.append(PlannedPolicyQuery(
            reason="recent_subscription_cancellation_flag is true",
            query="subscription cancellation recovery handling",
            expected_families=["subscriptions"],
            expected_doc_ids=[],
        ))

    if purchase_decline or engagement_decline:
        queries.append(PlannedPolicyQuery(
            reason="retention analysis must not infer causal discount uplift",
            query="exact causal uplift from retention discounts",
            expected_families=["governance"],
            expected_doc_ids=["GAP-001"],
        ))

    warning_signal = (
        purchase_decline
        or engagement_decline
        or support_attention
        or recent_subscription_cancel
    )
    if not warning_signal:
        queries.append(PlannedPolicyQuery(
            reason="no warning signals; retrieve general retention review guidance",
            query="retention investigation no action appropriate review guidance",
            expected_families=["retention"],
            expected_doc_ids=[],
        ))

    return queries


def combined_query(snapshot: dict[str, Any]) -> str:
    return " ".join(query.query for query in plan_policy_queries(snapshot))


class VectorPolicyRetriever:
    def __init__(
        self,
        *,
        embedder: OpenAIEmbedder,
        vector_store: PgVectorStore,
        per_query_top_k: int = 2,
        max_results: int = 12,
    ) -> None:
        if per_query_top_k <= 0 or max_results <= 0:
            raise ValueError("retrieval limits must be positive")
        self.embedder = embedder
        self.vector_store = vector_store
        self.per_query_top_k = per_query_top_k
        self.max_results = max_results
        self._query_vectors: dict[str, list[float]] = {}
        self.embedding_requests = 0
        self.embedding_input_tokens = 0

    def _vectors_for(self, queries: list[str]) -> dict[str, list[float]]:
        missing = list(dict.fromkeys(
            query for query in queries if query not in self._query_vectors
        ))
        if missing:
            run = self.embedder.embed(missing)
            self.embedding_requests += 1
            self.embedding_input_tokens += run.input_tokens
            self._query_vectors.update(zip(missing, run.vectors))
        return {query: self._query_vectors[query] for query in queries}

    def retrieve(
        self,
        snapshot: dict[str, Any],
    ) -> list[PolicyRetrievalResult]:
        planned_queries = plan_policy_queries(snapshot)
        vectors = self._vectors_for([query.query for query in planned_queries])
        by_doc_id: dict[str, PolicyRetrievalResult] = {}

        for planned_query in planned_queries:
            results = self.vector_store.search(
                vectors[planned_query.query],
                top_k=self.per_query_top_k,
                statuses={"CURRENT"},
                authorities={"APPROVED"},
            )
            for query_rank, vector_result in enumerate(results, start=1):
                candidate = PolicyRetrievalResult.from_vector_result(
                    vector_result,
                    planned_query,
                    query_rank,
                )
                existing = by_doc_id.get(candidate.document_id)
                if existing is None:
                    by_doc_id[candidate.document_id] = candidate
                    continue

                best = candidate if candidate.score > existing.score else existing
                by_doc_id[candidate.document_id] = replace(
                    best,
                    best_query_rank=min(
                        existing.best_query_rank,
                        candidate.best_query_rank,
                    ),
                    matched_queries=sorted(set(
                        existing.matched_queries + candidate.matched_queries
                    )),
                    retrieval_reasons=sorted(set(
                        existing.retrieval_reasons + candidate.retrieval_reasons
                    )),
                )

        return sorted(
            by_doc_id.values(),
            key=lambda result: (
                result.best_query_rank,
                -result.score,
                result.document_id,
            ),
        )[:self.max_results]


def expected_families(snapshot: dict[str, Any]) -> list[str]:
    families = {
        family
        for query in plan_policy_queries(snapshot)
        for family in query.expected_families
    }
    return sorted(families)


def expected_doc_ids(snapshot: dict[str, Any]) -> list[str]:
    doc_ids = {
        document_id
        for query in plan_policy_queries(snapshot)
        for document_id in query.expected_doc_ids
    }
    return sorted(doc_ids)
