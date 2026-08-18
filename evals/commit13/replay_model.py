from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from agents import Model, ModelResponse, ModelSettings
from agents.usage import Usage
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)

from src.actions import ActionProposal
from src.actions.schemas import CouponAction
from src.runtime_compare.agents_sdk import TOOL_NAME


class FrozenCouponToolCallModel(Model):
    """Deterministic model replay used to isolate runtime behavior."""

    def __init__(self, proposal: ActionProposal) -> None:
        if not isinstance(proposal.action, CouponAction):
            raise ValueError("replay model supports ISSUE_COUPON only")
        self.proposal = proposal
        self.calls = 0
        self.settings_observed: list[ModelSettings] = []

    async def get_response(
        self,
        system_instructions: str | None,
        input: str | list[Any],
        model_settings: ModelSettings,
        tools: list[Any],
        output_schema: Any,
        handoffs: list[Any],
        tracing: Any,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: Any,
    ) -> ModelResponse:
        del (
            system_instructions,
            tools,
            output_schema,
            handoffs,
            tracing,
            previous_response_id,
            conversation_id,
            prompt,
        )
        self.calls += 1
        self.settings_observed.append(model_settings)
        output = (
            self._final_message()
            if self._contains_tool_output(input)
            else self._tool_call()
        )
        return ModelResponse(
            output=[output],
            usage=Usage(),
            response_id=f"commit13-replay-{self.calls}",
        )

    def stream_response(self, *_: Any, **__: Any) -> AsyncIterator[Any]:
        async def empty_stream() -> AsyncIterator[Any]:
            if False:
                yield None

        return empty_stream()

    def _tool_call(self) -> ResponseFunctionToolCall:
        action = self.proposal.action
        return ResponseFunctionToolCall(
            type="function_call",
            name=TOOL_NAME,
            call_id=f"call-{self.proposal.action_id}",
            status="completed",
            arguments=json.dumps(
                {
                    "action_id": self.proposal.action_id,
                    "coupon_code": action.coupon_code,
                    "customer_id": self.proposal.customer_id,
                    "discount_percent": action.discount_percent,
                    "expires_in_days": action.expires_in_days,
                },
                sort_keys=True,
            ),
        )

    def _final_message(self) -> ResponseOutputMessage:
        return ResponseOutputMessage(
            id=f"message-{self.proposal.action_id}",
            type="message",
            role="assistant",
            status="completed",
            content=[ResponseOutputText(
                type="output_text",
                text="Action workflow completed.",
                annotations=[],
            )],
        )

    @staticmethod
    def _contains_tool_output(input: str | list[Any]) -> bool:
        if not isinstance(input, list):
            return False
        return any(
            (
                item.get("type")
                if isinstance(item, dict)
                else getattr(item, "type", None)
            ) == "function_call_output"
            for item in input
        )
