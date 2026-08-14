from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from typing import Any

from pydantic import ValidationError

from .pricing import estimate_text_cost_usd
from .prompts import PROMPT_VERSION, SYSTEM_INSTRUCTIONS, build_user_input
from .retry import with_exponential_backoff
from .schemas import CustomerAssessment


@dataclass
class LLMRunMetrics:
    response_id: str
    model: str
    prompt_version: str
    latency_seconds: float
    attempts: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    total_tokens: int
    estimated_cost_usd: float | None


@dataclass
class AssessmentResult:
    assessment: CustomerAssessment
    metrics: LLMRunMetrics
    raw_output_text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "assessment": self.assessment.model_dump(),
            "metrics": asdict(self.metrics),
            "raw_output_text": self.raw_output_text,
        }


class SignalDeskLLMClient:
    def __init__(
        self,
        *,
        model: str | None = None,
        reasoning_effort: str = "none",
        timeout_seconds: float = 30.0,
        max_attempts: int = 4,
    ):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install OpenAI SDK: pip install openai") from exc

        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-5.6-luna")
        self.reasoning_effort = reasoning_effort
        self.max_attempts = max_attempts

        # Disable SDK retries here so retry behavior is visible in our metrics.
        self._client = OpenAI(
            timeout=timeout_seconds,
            max_retries=0,
        )

    def assess(self, snapshot: dict[str, Any]) -> AssessmentResult:
        from openai import (
            APIConnectionError,
            APITimeoutError,
            InternalServerError,
            RateLimitError,
        )

        snapshot_json = json.dumps(
            snapshot,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )

        schema = CustomerAssessment.model_json_schema()

        def call():
            return self._client.responses.create(
                model=self.model,
                instructions=SYSTEM_INSTRUCTIONS,
                input=build_user_input(snapshot_json),
                reasoning={"effort": self.reasoning_effort},
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "customer_assessment",
                        "description": (
                            "Structured SignalDesk investigation assessment."
                        ),
                        "schema": schema,
                        "strict": True,
                    }
                },
                store=False,
                metadata={
                    "app": "signaldesk",
                    "prompt_version": PROMPT_VERSION,
                    "commit": "04",
                },
            )

        started = time.perf_counter()
        response, attempts = with_exponential_backoff(
            call,
            retryable_exceptions=(
                RateLimitError,
                APITimeoutError,
                APIConnectionError,
                InternalServerError,
            ),
            max_attempts=self.max_attempts,
        )
        latency = time.perf_counter() - started

        raw = response.output_text

        try:
            assessment = CustomerAssessment.model_validate_json(raw)
        except ValidationError as exc:
            raise RuntimeError(
                "OpenAI returned output that failed local Pydantic validation"
            ) from exc

        usage = response.usage
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        total_tokens = int(getattr(usage, "total_tokens", 0) or 0)

        input_details = getattr(usage, "input_tokens_details", None)
        output_details = getattr(usage, "output_tokens_details", None)

        cached_input_tokens = int(
            getattr(input_details, "cached_tokens", 0) or 0
        )
        reasoning_tokens = int(
            getattr(output_details, "reasoning_tokens", 0) or 0
        )

        metrics = LLMRunMetrics(
            response_id=response.id,
            model=response.model,
            prompt_version=PROMPT_VERSION,
            latency_seconds=round(latency, 4),
            attempts=attempts,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=estimate_text_cost_usd(
                self.model,
                input_tokens,
                cached_input_tokens,
                output_tokens,
            ),
        )

        return AssessmentResult(
            assessment=assessment,
            metrics=metrics,
            raw_output_text=raw,
        )
