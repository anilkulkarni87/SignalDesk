from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from src.actions.schemas import ActionProposal, ActionRun
from src.agent.schemas import AgentEvidence, StrictModel
from src.tools.schemas import CampaignEligibility, CustomerMetrics, CustomerProfile


class HealthView(StrictModel):
    status: Literal["ok"] = "ok"
    service: Literal["signaldesk-api"] = "signaldesk-api"
    version: Literal["commit15_v1"] = "commit15_v1"


class LoginRequest(StrictModel):
    access_code: str = Field(min_length=1, max_length=500)
    reviewer_id: str = Field(min_length=3, max_length=100)


class SessionView(StrictModel):
    user_id: str
    reviewer_id: str
    csrf_token: str
    expires_at: int


class CustomerSearchItem(StrictModel):
    customer_id: str
    customer_status: str
    loyalty_tier: str
    country: str
    days_since_last_seen: int
    warning_count: int = Field(ge=0, le=3)
    purchase_decline_flag: bool
    engagement_decline_flag: bool
    support_attention_flag: bool


class CustomerSearchView(StrictModel):
    query: str
    returned_count: int
    customers: list[CustomerSearchItem]


class Customer360View(StrictModel):
    customer_id: str
    profile: CustomerProfile
    metrics: CustomerMetrics
    campaign_eligibility: CampaignEligibility
    warning_count: int = Field(ge=0, le=3)


class InvestigationCreateRequest(StrictModel):
    customer_id: str = Field(pattern=r"^C\d{7}$")
    question: str = Field(min_length=10, max_length=1000)


class ToolExecutionView(StrictModel):
    round_number: int
    tool_name: str
    arguments: dict[str, Any] | None
    success: bool
    error_code: str | None
    latency_ms: float
    result_summary: str


class SourceView(StrictModel):
    document_id: str
    title: str
    family: str
    excerpt: str
    score: float
    cited: bool


class InvestigationMetricsView(StrictModel):
    model: str
    prompt_version: str
    reasoning_effort: Literal["none"]
    tool_calls: int
    model_rounds: int
    latency_seconds: float
    total_tokens: int
    estimated_cost_usd: float | None


class InvestigationView(StrictModel):
    investigation_id: str = Field(pattern=r"^INV-[a-f0-9]{20}$")
    customer_id: str
    question: str
    task_status: str
    conclusion_code: str
    risk_level: str
    summary: str
    evidence: list[AgentEvidence]
    limitations: list[str]
    policy_document_ids: list[str]
    tools: list[ToolExecutionView]
    sources: list[SourceView]
    timeline: list[str]
    metrics: InvestigationMetricsView
    created_at: str


class DraftSupportActionRequest(StrictModel):
    priority: Literal["LOW", "MEDIUM", "HIGH", "URGENT"] = "MEDIUM"
    reason: str = Field(min_length=10, max_length=500)


class ActionPackageView(StrictModel):
    investigation_id: str
    proposal: ActionProposal
    run: ActionRun


class ActionDecisionRequest(StrictModel):
    decision: Literal["APPROVED", "REJECTED"]
    reason: str = Field(min_length=3, max_length=500)
