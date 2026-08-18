from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from src.llm.pricing import estimate_text_cost_usd
from src.llm.retry import with_exponential_backoff
from src.tools.registry import ToolRegistry
from src.tools.schemas import ToolCallResult, ToolErrorDetail

from .prompts import PROMPT_VERSION, SYSTEM_INSTRUCTIONS, build_user_input
from .schemas import (
    READ_ONLY_AGENT_TOOLS,
    AgentRunMetrics,
    InvestigationAnswer,
    InvestigationRequest,
    InvestigationRun,
    ToolTrace,
)


CUSTOMER_SCOPED_TOOLS = frozenset(
    tool_name
    for tool_name in READ_ONLY_AGENT_TOOLS
    if tool_name != "search_knowledge_base"
)


class AgentExecutionError(RuntimeError):
    pass


class IncompleteAgentResponseError(AgentExecutionError):
    pass


class AgentLimitError(AgentExecutionError):
    pass


@dataclass(frozen=True)
class AgentConfig:
    model: str = "gpt-5.6-luna"
    reasoning_effort: str = "none"
    timeout_seconds: float = 45.0
    max_attempts: int = 4
    max_model_rounds: int = 8
    max_tool_calls: int = 8
    max_output_tokens: int = 1600

    def __post_init__(self) -> None:
        if self.reasoning_effort != "none":
            raise ValueError("Commit 10 freezes reasoning_effort=none")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if self.max_model_rounds < 1 or self.max_tool_calls < 1:
            raise ValueError("agent limits must be positive")


class CustomerInvestigator:
    def __init__(
        self,
        registry: ToolRegistry,
        *,
        config: AgentConfig | None = None,
        responses_client: Any | None = None,
    ) -> None:
        self.registry = registry
        self.config = config or AgentConfig()
        if responses_client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError("Install OpenAI from requirements-commit10.txt") from exc
            responses_client = OpenAI(
                timeout=self.config.timeout_seconds,
                max_retries=0,
            ).responses
        self._responses = responses_client
        self._retryable_errors = self._load_retryable_errors()
        self._tool_definitions = self._build_tool_definitions()

    @staticmethod
    def _load_retryable_errors() -> tuple[type[BaseException], ...]:
        try:
            from openai import (
                APIConnectionError,
                APITimeoutError,
                InternalServerError,
                RateLimitError,
            )
        except ImportError:
            return ()
        return (
            RateLimitError,
            APITimeoutError,
            APIConnectionError,
            InternalServerError,
        )

    def _build_tool_definitions(self) -> list[dict[str, Any]]:
        by_name = {
            definition["name"]: definition
            for definition in self.registry.definitions()
        }
        missing = sorted(set(READ_ONLY_AGENT_TOOLS) - set(by_name))
        if missing:
            raise ValueError(f"Registry is missing agent tools: {missing}")
        return [
            {
                "type": "function",
                "name": tool_name,
                "description": by_name[tool_name]["description"],
                "parameters": by_name[tool_name]["input_schema"],
                # The application registry remains the authoritative strict
                # validator and also supports defaults for bounded parameters.
                "strict": False,
            }
            for tool_name in READ_ONLY_AGENT_TOOLS
        ]

    def investigate(
        self,
        customer_id: str,
        question: str,
    ) -> InvestigationRun:
        request = InvestigationRequest(customer_id=customer_id, question=question)
        input_items: list[dict[str, Any]] = [{
            "role": "user",
            "content": [{
                "type": "input_text",
                "text": build_user_input(request),
            }],
        }]
        traces: list[ToolTrace] = []
        response_ids: list[str] = []
        totals = {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
            "total_tokens": 0,
            "api_attempts": 0,
        }
        started = time.perf_counter()

        for round_number in range(1, self.config.max_model_rounds + 1):
            def generate():
                return self._responses.create(
                    model=self.config.model,
                    instructions=SYSTEM_INSTRUCTIONS,
                    input=input_items,
                    reasoning={"effort": self.config.reasoning_effort},
                    max_output_tokens=self.config.max_output_tokens,
                    max_tool_calls=max(1, self.config.max_tool_calls - len(traces)),
                    parallel_tool_calls=True,
                    tools=self._tool_definitions,
                    tool_choice="auto",
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": "customer_investigation_answer",
                            "description": (
                                "Structured answer grounded in read-only CDP tool outputs."
                            ),
                            "schema": InvestigationAnswer.model_json_schema(),
                            "strict": True,
                        }
                    },
                    store=False,
                    metadata={
                        "app": "signaldesk",
                        "prompt_version": PROMPT_VERSION,
                        "commit": "10",
                    },
                )

            response, attempts = with_exponential_backoff(
                generate,
                retryable_exceptions=self._retryable_errors,
                max_attempts=self.config.max_attempts,
            )
            totals["api_attempts"] += attempts
            if getattr(response, "status", None) != "completed":
                raise IncompleteAgentResponseError(
                    f"Response {getattr(response, 'id', '<unknown>')} was not completed"
                )
            response_ids.append(response.id)
            self._add_usage(totals, response)

            function_calls = [
                item for item in response.output
                if self._item_value(item, "type") == "function_call"
            ]
            if not function_calls:
                raw_output_text = response.output_text
                try:
                    answer = InvestigationAnswer.model_validate_json(raw_output_text)
                except ValidationError as exc:
                    raise AgentExecutionError(
                        "Final response failed local InvestigationAnswer validation"
                    ) from exc
                metrics = AgentRunMetrics(
                    model=getattr(response, "model", self.config.model),
                    prompt_version=PROMPT_VERSION,
                    reasoning_effort="none",
                    response_ids=response_ids,
                    model_rounds=round_number,
                    tool_calls=len(traces),
                    api_requests=round_number,
                    api_attempts=totals["api_attempts"],
                    api_retry_attempts=totals["api_attempts"] - round_number,
                    input_tokens=totals["input_tokens"],
                    cached_input_tokens=totals["cached_input_tokens"],
                    output_tokens=totals["output_tokens"],
                    reasoning_tokens=totals["reasoning_tokens"],
                    total_tokens=totals["total_tokens"],
                    latency_seconds=round(time.perf_counter() - started, 4),
                    estimated_cost_usd=estimate_text_cost_usd(
                        self.config.model,
                        totals["input_tokens"],
                        totals["cached_input_tokens"],
                        totals["output_tokens"],
                    ),
                )
                return InvestigationRun(
                    request=request,
                    answer=answer,
                    tool_trace=traces,
                    metrics=metrics,
                    raw_output_text=raw_output_text,
                )

            if len(traces) + len(function_calls) > self.config.max_tool_calls:
                raise AgentLimitError("Agent exceeded max_tool_calls")

            input_items.extend(self._serialize_item(item) for item in response.output)
            for function_call in function_calls:
                tool_name = self._item_value(function_call, "name")
                raw_arguments = self._item_value(function_call, "arguments")
                call_id = self._item_value(function_call, "call_id")
                parsed_arguments = self._parse_arguments(raw_arguments)
                result = self._execute_bound_tool(
                    request.customer_id,
                    tool_name,
                    raw_arguments,
                    parsed_arguments,
                )
                traces.append(ToolTrace(
                    round_number=round_number,
                    call_id=call_id,
                    tool_name=tool_name,
                    arguments=parsed_arguments,
                    success=result.success,
                    error_code=result.error.code if result.error else None,
                    latency_ms=result.latency_ms,
                    output=result.output,
                ))
                input_items.append({
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": result.model_dump_json(),
                })

        raise AgentLimitError("Agent exceeded max_model_rounds without a final answer")

    def _execute_bound_tool(
        self,
        customer_id: str,
        tool_name: str,
        raw_arguments: str,
        parsed_arguments: dict[str, Any] | None,
    ) -> ToolCallResult:
        if tool_name in CUSTOMER_SCOPED_TOOLS and (
            parsed_arguments is None
            or parsed_arguments.get("customer_id") != customer_id
        ):
            return ToolCallResult(
                tool_name=tool_name,
                success=False,
                error=ToolErrorDetail(
                    code="CONFLICT",
                    message="Tool customer_id must match the investigation subject",
                ),
                latency_ms=0,
            )
        return self.registry.execute(tool_name, raw_arguments)

    @staticmethod
    def _parse_arguments(raw_arguments: str) -> dict[str, Any] | None:
        try:
            parsed = json.loads(raw_arguments)
        except (json.JSONDecodeError, TypeError):
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _item_value(item: Any, name: str) -> Any:
        return item.get(name) if isinstance(item, dict) else getattr(item, name)

    @staticmethod
    def _serialize_item(item: Any) -> dict[str, Any]:
        if isinstance(item, dict):
            return item
        return item.model_dump(mode="json", exclude_none=True)

    @staticmethod
    def _add_usage(totals: dict[str, int], response: Any) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        input_details = getattr(usage, "input_tokens_details", None)
        output_details = getattr(usage, "output_tokens_details", None)
        totals["input_tokens"] += input_tokens
        totals["cached_input_tokens"] += int(
            getattr(input_details, "cached_tokens", 0) or 0
        )
        totals["output_tokens"] += output_tokens
        totals["reasoning_tokens"] += int(
            getattr(output_details, "reasoning_tokens", 0) or 0
        )
        totals["total_tokens"] += int(
            getattr(usage, "total_tokens", input_tokens + output_tokens) or 0
        )
