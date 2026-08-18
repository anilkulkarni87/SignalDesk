from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.retrieval.documents import load_documents
from src.retrieval.lexical import LexicalIndex

from .errors import ToolConflictError, ToolNotFoundError
from .schemas import (
    CalculateCustomerMetricsInput,
    CampaignEligibility,
    ChannelEligibility,
    CreateRetentionRecommendationInput,
    CustomerEvents,
    CustomerMetrics,
    CustomerProfile,
    EvidenceValue,
    GetCampaignEligibilityInput,
    GetCustomerEventsInput,
    GetCustomerProfileInput,
    GetPurchaseHistoryInput,
    KnowledgeResult,
    KnowledgeSearchResults,
    PurchaseHistory,
    PurchaseItem,
    PurchaseOrder,
    RetentionRecommendationDraft,
    SearchKnowledgeBaseInput,
)


PROFILE_COLUMNS = (
    "customer_id",
    "as_of_ts",
    "profile_created_at",
    "customer_status",
    "loyalty_tier",
    "country",
    "timezone",
    "days_since_last_seen",
    "resolved_identity_count",
)

METRIC_GROUPS = {
    "purchase": (
        "lifetime_orders",
        "lifetime_value",
        "orders_30d",
        "orders_60d",
        "orders_90d",
        "orders_prior_60d",
        "revenue_60d",
        "revenue_prior_60d",
        "days_since_purchase",
        "avg_order_value_lifetime",
        "refund_rate_90d",
        "purchase_change_pct",
        "preferred_category",
        "purchase_decline_flag",
    ),
    "engagement": (
        "sessions_30d",
        "sessions_60d",
        "sessions_90d",
        "sessions_prior_60d",
        "session_change_pct",
        "product_views_60d",
        "add_to_cart_60d",
        "checkout_starts_60d",
        "channel_affinity",
        "engagement_decline_flag",
    ),
    "support": (
        "support_cases_lifetime",
        "support_cases_90d",
        "open_support_cases",
        "negative_support_cases_90d",
        "high_priority_support_cases_90d",
        "days_since_last_support_case",
        "avg_csat_90d",
        "support_attention_flag",
    ),
    "campaigns": (
        "campaigns_delivered_90d",
        "email_delivered_90d",
        "email_opens_90d",
        "email_clicks_90d",
        "email_open_rate_90d",
        "email_click_rate_90d",
        "email_engagement",
        "days_since_last_campaign",
    ),
    "subscriptions_and_consent": (
        "active_subscription_count",
        "recent_subscription_cancellation_flag",
        "email_opted_in",
        "sms_opted_in",
        "push_opted_in",
    ),
}


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


class CDPTools:
    """Read-only tool implementations over the NovaCart semantic layer."""

    def __init__(
        self,
        database: str | Path,
        *,
        corpus_dir: str | Path = "data/generated/knowledge",
    ) -> None:
        try:
            import duckdb
        except ImportError as exc:
            raise RuntimeError("Install DuckDB from requirements-commit09.txt") from exc

        self._connection = duckdb.connect(str(database), read_only=True)
        documents = load_documents(corpus_dir)
        self._policy_documents = {
            document.document_id: document
            for document in documents
            if document.status == "CURRENT" and document.authority == "APPROVED"
        }
        self._knowledge_index = LexicalIndex(list(self._policy_documents.values()))

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "CDPTools":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()

    def _customer_snapshot(self, customer_id: str) -> dict[str, Any]:
        row = self._connection.execute(
            "SELECT * FROM customer_360 WHERE customer_id = ?",
            [customer_id],
        ).fetchone()
        if row is None:
            raise ToolNotFoundError(f"Unknown customer_id: {customer_id}")
        names = [column[0] for column in self._connection.description]
        return {
            name: json_safe(value)
            for name, value in zip(names, row)
        }

    def get_customer_profile(
        self,
        request: GetCustomerProfileInput,
    ) -> CustomerProfile:
        snapshot = self._customer_snapshot(request.customer_id)
        return CustomerProfile(**{
            column: snapshot[column] for column in PROFILE_COLUMNS
        })

    def get_customer_events(
        self,
        request: GetCustomerEventsInput,
    ) -> CustomerEvents:
        snapshot = self._customer_snapshot(request.customer_id)
        filters = [
            "resolved_customer_id = ?",
            "event_timestamp > CAST(? AS TIMESTAMPTZ) - (? * INTERVAL '1 day')",
            "event_timestamp <= CAST(? AS TIMESTAMPTZ)",
        ]
        params: list[Any] = [
            request.customer_id,
            snapshot["as_of_ts"],
            request.days,
            snapshot["as_of_ts"],
        ]
        if request.event_types:
            placeholders = ", ".join("?" for _ in request.event_types)
            filters.append(f"event_type IN ({placeholders})")
            params.extend(request.event_types)
        where = " AND ".join(filters)
        total_count = self._connection.execute(
            f"SELECT COUNT(*) FROM stg_events WHERE {where}",
            params,
        ).fetchone()[0]
        rows = self._connection.execute(
            f"""
            SELECT event_id, event_type, event_timestamp, received_at,
                   product_id, order_id
            FROM stg_events
            WHERE {where}
            ORDER BY event_timestamp DESC, event_id
            LIMIT ?
            """,
            [*params, request.limit],
        ).fetchall()
        events = [
            {
                "event_id": row[0],
                "event_type": row[1],
                "event_timestamp": json_safe(row[2]),
                "received_at": json_safe(row[3]),
                "product_id": row[4],
                "order_id": row[5],
            }
            for row in rows
        ]
        return CustomerEvents(
            customer_id=request.customer_id,
            as_of_ts=snapshot["as_of_ts"],
            window_days=request.days,
            event_types=request.event_types,
            returned_count=len(events),
            total_count=total_count,
            truncated=total_count > len(events),
            events=events,
        )

    def get_purchase_history(
        self,
        request: GetPurchaseHistoryInput,
    ) -> PurchaseHistory:
        snapshot = self._customer_snapshot(request.customer_id)
        window_params = [
            request.customer_id,
            snapshot["as_of_ts"],
            request.days,
            snapshot["as_of_ts"],
        ]
        where = (
            "customer_id = ? "
            "AND order_timestamp > CAST(? AS TIMESTAMPTZ) - (? * INTERVAL '1 day') "
            "AND order_timestamp <= CAST(? AS TIMESTAMPTZ)"
        )
        total_count = self._connection.execute(
            f"SELECT COUNT(*) FROM stg_orders WHERE {where}",
            window_params,
        ).fetchone()[0]
        order_rows = self._connection.execute(
            f"""
            SELECT order_id, order_timestamp, status, channel,
                   total_amount, discount_amount
            FROM stg_orders
            WHERE {where}
            ORDER BY order_timestamp DESC, order_id
            LIMIT ?
            """,
            [*window_params, request.limit],
        ).fetchall()
        order_ids = [row[0] for row in order_rows]
        items_by_order: dict[str, list[PurchaseItem]] = {
            order_id: [] for order_id in order_ids
        }
        if order_ids:
            placeholders = ", ".join("?" for _ in order_ids)
            item_rows = self._connection.execute(
                f"""
                SELECT i.order_id, i.order_item_id, i.product_id,
                       p.category, p.subcategory, p.brand,
                       i.quantity, i.unit_price, i.line_discount, i.line_total
                FROM stg_order_items i
                JOIN stg_products p USING (product_id)
                WHERE i.order_id IN ({placeholders})
                ORDER BY i.order_id, i.order_item_id
                """,
                order_ids,
            ).fetchall()
            for row in item_rows:
                items_by_order[row[0]].append(PurchaseItem(
                    order_item_id=row[1],
                    product_id=row[2],
                    category=row[3],
                    subcategory=row[4],
                    brand=row[5],
                    quantity=row[6],
                    unit_price=row[7],
                    line_discount=row[8],
                    line_total=row[9],
                ))
        orders = [
            PurchaseOrder(
                order_id=row[0],
                order_timestamp=json_safe(row[1]),
                status=row[2],
                channel=row[3],
                total_amount=row[4],
                discount_amount=row[5],
                items=items_by_order[row[0]],
            )
            for row in order_rows
        ]
        return PurchaseHistory(
            customer_id=request.customer_id,
            as_of_ts=snapshot["as_of_ts"],
            window_days=request.days,
            returned_count=len(orders),
            total_count=total_count,
            truncated=total_count > len(orders),
            orders=orders,
        )

    def search_knowledge_base(
        self,
        request: SearchKnowledgeBaseInput,
    ) -> KnowledgeSearchResults:
        results = self._knowledge_index.search(
            request.query,
            top_k=request.top_k,
            families=set(request.families) if request.families else None,
        )
        return KnowledgeSearchResults(
            query=request.query,
            families=request.families,
            retrieval_method="lexical_current_approved",
            returned_count=len(results),
            results=[KnowledgeResult(
                document_id=result.document_id,
                title=result.title,
                family=result.family,
                status=result.status,
                authority=result.authority,
                score=result.score,
                matched_terms=result.matched_terms,
                excerpt=result.excerpt,
                source_path=result.path,
            ) for result in results],
        )

    def calculate_customer_metrics(
        self,
        request: CalculateCustomerMetricsInput,
    ) -> CustomerMetrics:
        snapshot = self._customer_snapshot(request.customer_id)
        return CustomerMetrics(
            customer_id=request.customer_id,
            as_of_ts=snapshot["as_of_ts"],
            **{
                group: {feature: snapshot[feature] for feature in features}
                for group, features in METRIC_GROUPS.items()
            },
        )

    def get_campaign_eligibility(
        self,
        request: GetCampaignEligibilityInput,
    ) -> CampaignEligibility:
        snapshot = self._customer_snapshot(request.customer_id)
        channels = [request.channel] if request.channel else ["EMAIL", "SMS", "PUSH"]
        channel_results = []
        for channel in channels:
            consented = bool(snapshot[f"{channel.lower()}_opted_in"])
            reasons = []
            if snapshot["customer_status"] != "ACTIVE":
                reasons.append(
                    f"customer_status is {snapshot['customer_status']}, not ACTIVE"
                )
            if not consented:
                reasons.append(f"{channel} consent is not opted in")
            status = "BLOCKED" if reasons else "REVIEW_REQUIRED"
            if not reasons:
                reasons.append(
                    "channel consent permits review but does not establish campaign eligibility"
                )
            channel_results.append(ChannelEligibility(
                channel=channel,
                consented=consented,
                status=status,
                reasons=reasons,
            ))

        overall = (
            "REVIEW_REQUIRED"
            if any(result.status == "REVIEW_REQUIRED" for result in channel_results)
            else "BLOCKED"
        )
        limitations = [
            "No campaign definition, audience rule, or offer terms were supplied.",
            "Current approved campaign, consent, and offer policies require review.",
        ]
        if snapshot["support_attention_flag"]:
            limitations.append(
                "An unresolved support signal should be reviewed before retention outreach."
            )
        return CampaignEligibility(
            customer_id=request.customer_id,
            as_of_ts=snapshot["as_of_ts"],
            status=overall,
            channel_results=channel_results,
            support_attention_flag=snapshot["support_attention_flag"],
            days_since_last_campaign=snapshot["days_since_last_campaign"],
            limitations=limitations,
        )

    def create_retention_recommendation(
        self,
        request: CreateRetentionRecommendationInput,
    ) -> RetentionRecommendationDraft:
        snapshot = self._customer_snapshot(request.customer_id)
        missing_documents = [
            document_id
            for document_id in request.policy_document_ids
            if document_id not in self._policy_documents
        ]
        if missing_documents:
            raise ToolNotFoundError(
                "Unknown or non-authoritative policy document IDs: "
                + ", ".join(missing_documents)
            )

        if request.recommendation == "RETENTION_OFFER":
            eligibility = self.get_campaign_eligibility(
                GetCampaignEligibilityInput(customer_id=request.customer_id)
            )
            if eligibility.status == "BLOCKED":
                raise ToolConflictError(
                    "Retention offer draft is blocked for every communication channel"
                )

        evidence = [
            EvidenceValue(feature=feature, value=snapshot[feature])
            for feature in request.evidence_features
        ]
        canonical = json.dumps({
            "customer_id": request.customer_id,
            "as_of_ts": snapshot["as_of_ts"],
            "recommendation": request.recommendation,
            "rationale": request.rationale,
            "evidence_features": request.evidence_features,
            "policy_document_ids": request.policy_document_ids,
        }, sort_keys=True, separators=(",", ":"))
        recommendation_id = "DRAFT-" + hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest()[:12].upper()
        return RetentionRecommendationDraft(
            recommendation_id=recommendation_id,
            customer_id=request.customer_id,
            as_of_ts=snapshot["as_of_ts"],
            recommendation=request.recommendation,
            rationale=request.rationale,
            evidence=evidence,
            policy_document_ids=request.policy_document_ids,
            limitations=[
                "Policy IDs are verified as current and approved, but this tool does "
                "not evaluate whether each policy semantically supports the rationale.",
                "The draft is not persisted or executed.",
            ],
        )
