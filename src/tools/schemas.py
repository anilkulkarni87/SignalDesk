from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.llm.schemas import EvidenceFeature


CustomerId = str
Channel = Literal["EMAIL", "SMS", "PUSH"]
EventType = Literal[
    "add_to_cart",
    "checkout_started",
    "page_view",
    "product_view",
    "purchase_completed",
    "search",
]
KnowledgeFamily = Literal[
    "campaigns",
    "consent",
    "governance",
    "loyalty",
    "offers",
    "refunds",
    "retention",
    "shipping",
    "subscriptions",
    "support",
]
RecommendationType = Literal[
    "NO_ACTION",
    "INVESTIGATE",
    "RETENTION_OFFER",
    "ESCALATE_TO_SUPPORT",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CustomerInput(StrictModel):
    customer_id: CustomerId = Field(pattern=r"^C\d{7}$")


class GetCustomerProfileInput(CustomerInput):
    pass


class GetCustomerEventsInput(CustomerInput):
    days: int = Field(default=30, ge=1, le=90)
    limit: int = Field(default=50, ge=1, le=100)
    event_types: list[EventType] = Field(default_factory=list, max_length=6)


class GetPurchaseHistoryInput(CustomerInput):
    days: int = Field(default=365, ge=1, le=730)
    limit: int = Field(default=20, ge=1, le=50)


class SearchKnowledgeBaseInput(StrictModel):
    query: str = Field(min_length=3, max_length=500)
    top_k: int = Field(default=5, ge=1, le=10)
    families: list[KnowledgeFamily] = Field(default_factory=list, max_length=5)


class CalculateCustomerMetricsInput(CustomerInput):
    pass


class GetCampaignEligibilityInput(CustomerInput):
    channel: Channel | None = None


class CreateRetentionRecommendationInput(CustomerInput):
    recommendation: RecommendationType
    rationale: str = Field(min_length=10, max_length=1000)
    evidence_features: list[EvidenceFeature] = Field(min_length=1, max_length=8)
    policy_document_ids: list[str] = Field(min_length=1, max_length=8)

    @field_validator("evidence_features", "policy_document_ids")
    @classmethod
    def unique_values(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("values must be unique")
        return value

    @field_validator("policy_document_ids")
    @classmethod
    def valid_policy_ids(cls, value: list[str]) -> list[str]:
        for document_id in value:
            if not (
                document_id.startswith("KB-") or document_id.startswith("GAP-")
            ):
                raise ValueError("policy IDs must start with KB- or GAP-")
        return value


class CustomerProfile(StrictModel):
    customer_id: str
    as_of_ts: str
    profile_created_at: str
    customer_status: str
    loyalty_tier: str
    country: str
    timezone: str
    days_since_last_seen: int
    resolved_identity_count: int
    pii_included: Literal[False] = False


class CustomerEvent(StrictModel):
    event_id: str
    event_type: EventType
    event_timestamp: str
    received_at: str
    product_id: str | None
    order_id: str | None


class CustomerEvents(StrictModel):
    customer_id: str
    as_of_ts: str
    window_days: int
    event_types: list[EventType]
    returned_count: int
    total_count: int
    truncated: bool
    events: list[CustomerEvent]


class PurchaseItem(StrictModel):
    order_item_id: str
    product_id: str
    category: str
    subcategory: str
    brand: str
    quantity: int
    unit_price: float
    line_discount: float
    line_total: float


class PurchaseOrder(StrictModel):
    order_id: str
    order_timestamp: str
    status: Literal["CANCELED", "COMPLETED", "REFUNDED", "SHIPPED"]
    channel: str
    total_amount: float
    discount_amount: float
    items: list[PurchaseItem]


class PurchaseHistory(StrictModel):
    customer_id: str
    as_of_ts: str
    window_days: int
    returned_count: int
    total_count: int
    truncated: bool
    orders: list[PurchaseOrder]


class CustomerMetrics(StrictModel):
    customer_id: str
    as_of_ts: str
    purchase: dict[str, Any]
    engagement: dict[str, Any]
    support: dict[str, Any]
    campaigns: dict[str, Any]
    subscriptions_and_consent: dict[str, Any]
    provenance: Literal["customer_360"] = "customer_360"


class KnowledgeResult(StrictModel):
    document_id: str
    title: str
    family: KnowledgeFamily
    status: Literal["CURRENT"]
    authority: Literal["APPROVED"]
    score: float
    matched_terms: list[str]
    excerpt: str
    source_path: str


class KnowledgeSearchResults(StrictModel):
    query: str
    families: list[KnowledgeFamily]
    retrieval_method: Literal["lexical_current_approved"]
    returned_count: int
    results: list[KnowledgeResult]


class ChannelEligibility(StrictModel):
    channel: Channel
    consented: bool
    status: Literal["BLOCKED", "REVIEW_REQUIRED"]
    reasons: list[str]


class CampaignEligibility(StrictModel):
    customer_id: str
    as_of_ts: str
    status: Literal["BLOCKED", "REVIEW_REQUIRED"]
    channel_results: list[ChannelEligibility]
    support_attention_flag: bool
    days_since_last_campaign: int | None
    limitations: list[str]


class EvidenceValue(StrictModel):
    feature: EvidenceFeature
    value: Any


class RetentionRecommendationDraft(StrictModel):
    recommendation_id: str
    customer_id: str
    as_of_ts: str
    recommendation: RecommendationType
    rationale: str
    evidence: list[EvidenceValue]
    policy_document_ids: list[str]
    limitations: list[str]
    status: Literal["DRAFT"] = "DRAFT"
    requires_human_approval: Literal[True] = True
    execution_allowed: Literal[False] = False
    persisted: Literal[False] = False


class ToolErrorDetail(StrictModel):
    code: Literal[
        "VALIDATION_ERROR",
        "NOT_FOUND",
        "CONFLICT",
        "UNKNOWN_TOOL",
        "INTERNAL_ERROR",
    ]
    message: str
    details: list[dict[str, Any]] = Field(default_factory=list)


class ToolCallResult(StrictModel):
    tool_name: str
    success: bool
    output: dict[str, Any] | None = None
    error: ToolErrorDetail | None = None
    latency_ms: float = Field(ge=0)

    @model_validator(mode="after")
    def consistent_envelope(self) -> "ToolCallResult":
        if self.success and (self.output is None or self.error is not None):
            raise ValueError("successful results require output and forbid errors")
        if not self.success and (self.error is None or self.output is not None):
            raise ValueError("failed results require an error and forbid output")
        return self
