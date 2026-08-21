from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from src.agent.schemas import StrictModel


RunStatus = Literal["SUCCESS", "ERROR"]
EvaluationResult = Literal["NOT_EVALUATED", "PASS", "FAIL"]


class ObservedToolCall(StrictModel):
    round_number: int = Field(ge=1)
    tool_name: str
    success: bool
    error_code: str | None
    latency_ms: float = Field(ge=0)
    returned_count: int | None = Field(default=None, ge=0)


class ObservedTokenUsage(StrictModel):
    input: int = Field(ge=0)
    cached_input: int = Field(ge=0)
    output: int = Field(ge=0)
    reasoning: int = Field(ge=0)
    total: int = Field(ge=0)


class ObservedError(StrictModel):
    stage: str
    error_type: str
    message: str = Field(max_length=500)


class RunObservation(StrictModel):
    request_id: str = Field(pattern=r"^REQ-[a-f0-9]{20}$")
    investigation_id: str | None = None
    user_id: str
    customer_id: str
    question: str
    status: RunStatus
    task_success: bool
    model: str
    prompt_version: str
    reasoning_effort: Literal["none"]
    tool_calls: list[ObservedToolCall]
    retrieval_documents: list[str]
    retrieval_scores: list[float]
    tokens: ObservedTokenUsage
    cost_usd: float | None = Field(default=None, ge=0)
    latency_seconds: float = Field(ge=0)
    final_answer: dict[str, Any] | None
    evaluation_result: EvaluationResult = "NOT_EVALUATED"
    evaluation_note: str | None = Field(default=None, max_length=500)
    errors: list[ObservedError]
    started_at: str
    completed_at: str

    @model_validator(mode="after")
    def fields_match_status(self) -> "RunObservation":
        if len(self.retrieval_documents) != len(self.retrieval_scores):
            raise ValueError("retrieval documents and scores must align")
        if self.status == "SUCCESS":
            if self.investigation_id is None or self.final_answer is None:
                raise ValueError("successful runs require an investigation and answer")
        elif self.final_answer is not None or not self.errors:
            raise ValueError("failed runs require errors and no final answer")
        if self.evaluation_result == "NOT_EVALUATED" and self.evaluation_note:
            raise ValueError("unevaluated runs cannot have an evaluation note")
        return self


class LatencySummary(StrictModel):
    p50: float
    p95: float


class ObservabilitySummary(StrictModel):
    total_runs: int = Field(ge=0)
    successful_runs: int = Field(ge=0)
    error_runs: int = Field(ge=0)
    task_success_rate_pct: float
    latency_seconds: LatencySummary
    tokens_per_task: float
    cost_per_task_usd: float
    tool_failure_rate_pct: float
    retrieval_failure_rate_pct: float
    evaluated_runs: int = Field(ge=0)
    evaluation_pass_rate_pct: float | None


class RunObservationList(StrictModel):
    runs: list[RunObservation]


class EvaluationUpdate(StrictModel):
    result: Literal["PASS", "FAIL"]
    note: str = Field(min_length=3, max_length=500)
