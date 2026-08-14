from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# Every non-ID/context field that the model is allowed to use materially should
# also be citable as evidence. This closes the v1 gap where customer_status
# could influence the summary/risk classification but could not be cited.
EvidenceFeature = Literal[
    "customer_status",
    "loyalty_tier",
    "days_since_last_seen",
    "lifetime_orders",
    "lifetime_value",
    "orders_30d",
    "orders_60d",
    "orders_90d",
    "orders_prior_60d",
    "revenue_60d",
    "revenue_prior_60d",
    "days_since_purchase",
    "refund_rate_90d",
    "purchase_change_pct",
    "preferred_category",
    "purchase_decline_flag",
    "sessions_30d",
    "sessions_60d",
    "sessions_90d",
    "sessions_prior_60d",
    "session_change_pct",
    "product_views_60d",
    "add_to_cart_60d",
    "engagement_decline_flag",
    "support_cases_90d",
    "open_support_cases",
    "negative_support_cases_90d",
    "high_priority_support_cases_90d",
    "avg_csat_90d",
    "support_attention_flag",
    "email_delivered_90d",
    "email_opens_90d",
    "email_clicks_90d",
    "email_open_rate_90d",
    "email_click_rate_90d",
    "email_engagement",
    "active_subscription_count",
    "recent_subscription_cancellation_flag",
    "email_opted_in",
    "sms_opted_in",
    "push_opted_in",
]

InvestigationArea = Literal[
    "PURCHASE_HISTORY",
    "BEHAVIORAL_ENGAGEMENT",
    "SUPPORT_HISTORY",
    "CAMPAIGN_ENGAGEMENT",
    "SUBSCRIPTIONS",
    "CONSENT",
    "NO_FURTHER_INVESTIGATION",
]

RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]


class EvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature: EvidenceFeature
    interpretation: str = Field(min_length=1, max_length=240)


class CustomerAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_level: RiskLevel
    summary: str = Field(min_length=1, max_length=500)
    evidence: list[EvidenceReference] = Field(min_length=1, max_length=8)
    recommended_investigation: list[InvestigationArea] = Field(
        min_length=1,
        max_length=6,
    )
    limitations: list[str] = Field(max_length=5)


LLM_FEATURES: tuple[str, ...] = (
    "customer_id",
    "as_of_ts",
    "loyalty_tier",
    "customer_status",
    "days_since_last_seen",
    "lifetime_orders",
    "lifetime_value",
    "orders_30d",
    "orders_60d",
    "orders_90d",
    "orders_prior_60d",
    "revenue_60d",
    "revenue_prior_60d",
    "days_since_purchase",
    "refund_rate_90d",
    "purchase_change_pct",
    "preferred_category",
    "purchase_decline_flag",
    "sessions_30d",
    "sessions_60d",
    "sessions_90d",
    "sessions_prior_60d",
    "session_change_pct",
    "product_views_60d",
    "add_to_cart_60d",
    "engagement_decline_flag",
    "support_cases_90d",
    "open_support_cases",
    "negative_support_cases_90d",
    "high_priority_support_cases_90d",
    "avg_csat_90d",
    "support_attention_flag",
    "email_delivered_90d",
    "email_opens_90d",
    "email_clicks_90d",
    "email_open_rate_90d",
    "email_click_rate_90d",
    "email_engagement",
    "active_subscription_count",
    "recent_subscription_cancellation_flag",
    "email_opted_in",
    "sms_opted_in",
    "push_opted_in",
)
