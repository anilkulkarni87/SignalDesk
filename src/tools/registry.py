from __future__ import annotations

import json
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from .cdp import CDPTools
from .errors import ToolConflictError, ToolError, ToolNotFoundError
from .schemas import (
    CalculateCustomerMetricsInput,
    CampaignEligibility,
    CreateRetentionRecommendationInput,
    CustomerEvents,
    CustomerMetrics,
    CustomerProfile,
    GetCampaignEligibilityInput,
    GetCustomerEventsInput,
    GetCustomerProfileInput,
    GetPurchaseHistoryInput,
    KnowledgeSearchResults,
    PurchaseHistory,
    RetentionRecommendationDraft,
    SearchKnowledgeBaseInput,
    ToolCallResult,
    ToolErrorDetail,
)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Callable[[BaseModel], BaseModel]

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_model.model_json_schema(),
            "output_schema": self.output_model.model_json_schema(),
            "side_effects": "none",
        }


class ToolRegistry:
    def __init__(self, tools: CDPTools) -> None:
        specs = [
            ToolSpec(
                name="get_customer_profile",
                description=(
                    "Return the PII-safe customer profile and semantic-layer as-of time."
                ),
                input_model=GetCustomerProfileInput,
                output_model=CustomerProfile,
                handler=tools.get_customer_profile,
            ),
            ToolSpec(
                name="get_customer_events",
                description=(
                    "Return bounded, identity-resolved customer events in an explicit "
                    "lookback window."
                ),
                input_model=GetCustomerEventsInput,
                output_model=CustomerEvents,
                handler=tools.get_customer_events,
            ),
            ToolSpec(
                name="get_purchase_history",
                description=(
                    "Return bounded customer orders and product-line evidence in an "
                    "explicit lookback window."
                ),
                input_model=GetPurchaseHistoryInput,
                output_model=PurchaseHistory,
                handler=tools.get_purchase_history,
            ),
            ToolSpec(
                name="search_knowledge_base",
                description=(
                    "Search only current, approved knowledge documents using a bounded "
                    "deterministic lexical index."
                ),
                input_model=SearchKnowledgeBaseInput,
                output_model=KnowledgeSearchResults,
                handler=tools.search_knowledge_base,
            ),
            ToolSpec(
                name="calculate_customer_metrics",
                description=(
                    "Return deterministic Customer 360 metrics grouped by business domain."
                ),
                input_model=CalculateCustomerMetricsInput,
                output_model=CustomerMetrics,
                handler=tools.calculate_customer_metrics,
            ),
            ToolSpec(
                name="get_campaign_eligibility",
                description=(
                    "Return hard customer/channel blocks and review requirements; this "
                    "does not claim final campaign or offer eligibility."
                ),
                input_model=GetCampaignEligibilityInput,
                output_model=CampaignEligibility,
                handler=tools.get_campaign_eligibility,
            ),
            ToolSpec(
                name="create_retention_recommendation",
                description=(
                    "Create a deterministic, non-persisted draft recommendation from "
                    "explicit evidence and current approved policy IDs. Never execute it."
                ),
                input_model=CreateRetentionRecommendationInput,
                output_model=RetentionRecommendationDraft,
                handler=tools.create_retention_recommendation,
            ),
        ]
        self._specs = {spec.name: spec for spec in specs}

    def definitions(self) -> list[dict[str, Any]]:
        return [self._specs[name].schema() for name in sorted(self._specs)]

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any] | str,
    ) -> ToolCallResult:
        started = perf_counter()
        spec = self._specs.get(tool_name)
        if spec is None:
            return self._failure(
                tool_name,
                started,
                code="UNKNOWN_TOOL",
                message=f"Unknown tool: {tool_name}",
            )

        try:
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            validated_input = spec.input_model.model_validate(arguments)
            raw_output = spec.handler(validated_input)
            output = spec.output_model.model_validate(raw_output)
            return ToolCallResult(
                tool_name=tool_name,
                success=True,
                output=output.model_dump(mode="json"),
                latency_ms=round((perf_counter() - started) * 1000, 3),
            )
        except (ValidationError, json.JSONDecodeError) as exc:
            details = exc.errors(include_url=False) if isinstance(exc, ValidationError) else []
            return self._failure(
                tool_name,
                started,
                code="VALIDATION_ERROR",
                message="Tool arguments failed validation",
                details=details,
            )
        except ToolError as exc:
            code = (
                "NOT_FOUND" if isinstance(exc, ToolNotFoundError)
                else "CONFLICT" if isinstance(exc, ToolConflictError)
                else "INTERNAL_ERROR"
            )
            return self._failure(
                tool_name,
                started,
                code=code,
                message=str(exc),
            )
        except Exception:
            return self._failure(
                tool_name,
                started,
                code="INTERNAL_ERROR",
                message="Tool execution failed",
            )

    @staticmethod
    def _failure(
        tool_name: str,
        started: float,
        *,
        code: str,
        message: str,
        details: list[dict[str, Any]] | None = None,
    ) -> ToolCallResult:
        return ToolCallResult(
            tool_name=tool_name,
            success=False,
            error=ToolErrorDetail(
                code=code,
                message=message,
                details=details or [],
            ),
            latency_ms=round((perf_counter() - started) * 1000, 3),
        )
