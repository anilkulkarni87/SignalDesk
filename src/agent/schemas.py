from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


READ_ONLY_AGENT_TOOLS = (
    "calculate_customer_metrics",
    "get_campaign_eligibility",
    "get_customer_events",
    "get_customer_profile",
    "get_purchase_history",
    "search_knowledge_base",
)

ReadOnlyToolName = Literal[
    "calculate_customer_metrics",
    "get_campaign_eligibility",
    "get_customer_events",
    "get_customer_profile",
    "get_purchase_history",
    "search_knowledge_base",
]

ConclusionCode = Literal[
    "PROFILE_REPORTED",
    "MULTIPLE_WARNING_SIGNALS",
    "PURCHASE_DECLINE",
    "ENGAGEMENT_DECLINE",
    "SUPPORT_ATTENTION",
    "NO_WARNING_SIGNALS",
    "CAMPAIGN_BLOCKED",
    "CAMPAIGN_REVIEW_REQUIRED",
    "INSUFFICIENT_EVIDENCE",
]

RiskLevel = Literal["NOT_ASSESSED", "LOW", "MEDIUM", "HIGH"]
JsonScalar = str | int | float | bool | None


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class InvestigationRequest(StrictModel):
    customer_id: str = Field(pattern=r"^C\d{7}$")
    question: str = Field(min_length=10, max_length=1000)


class AgentEvidence(StrictModel):
    source_tool: ReadOnlyToolName
    field: str = Field(min_length=1, max_length=100)
    value: JsonScalar
    interpretation: str = Field(min_length=1, max_length=300)


class InvestigationAnswer(StrictModel):
    customer_id: str = Field(pattern=r"^C\d{7}$")
    task_status: Literal["COMPLETED", "LIMITED"]
    conclusion_code: ConclusionCode
    risk_level: RiskLevel
    summary: str = Field(min_length=1, max_length=400)
    evidence: list[AgentEvidence] = Field(min_length=1, max_length=10)
    policy_document_ids: list[str] = Field(max_length=8)
    limitations: list[str] = Field(max_length=5)

    @field_validator("policy_document_ids")
    @classmethod
    def unique_policy_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("policy document IDs must be unique")
        return value


class ToolTrace(StrictModel):
    round_number: int = Field(ge=1)
    call_id: str
    tool_name: str
    arguments: dict[str, Any] | None
    success: bool
    error_code: str | None
    latency_ms: float = Field(ge=0)
    output: dict[str, Any] | None


class AgentRunMetrics(StrictModel):
    model: str
    prompt_version: str
    reasoning_effort: Literal["none"]
    response_ids: list[str]
    model_rounds: int = Field(ge=1)
    tool_calls: int = Field(ge=0)
    api_requests: int = Field(ge=1)
    api_attempts: int = Field(ge=1)
    api_retry_attempts: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    reasoning_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    latency_seconds: float = Field(ge=0)
    estimated_cost_usd: float | None


class InvestigationRun(StrictModel):
    request: InvestigationRequest
    answer: InvestigationAnswer
    tool_trace: list[ToolTrace]
    metrics: AgentRunMetrics
    raw_output_text: str

    @model_validator(mode="after")
    def answer_matches_subject(self) -> "InvestigationRun":
        if self.answer.customer_id != self.request.customer_id:
            raise ValueError("answer customer_id must match request customer_id")
        return self
