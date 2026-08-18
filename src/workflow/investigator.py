from __future__ import annotations

import time
from typing import Any, Literal, TypedDict
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from src.agent.investigator import (
    AgentConfig,
    AgentExecutionError,
    AgentLimitError,
    CustomerInvestigator,
    IncompleteAgentResponseError,
)
from src.agent.prompts import PROMPT_VERSION, SYSTEM_INSTRUCTIONS, build_user_input
from src.agent.schemas import (
    AgentRunMetrics,
    InvestigationAnswer,
    InvestigationRequest,
    ToolTrace,
)
from src.llm.pricing import estimate_text_cost_usd
from src.llm.retry import with_exponential_backoff
from src.tools.registry import ToolRegistry

from .schemas import WorkflowMetrics, WorkflowRoute, WorkflowRun


WORKFLOW_VERSION = "commit11_v1_explicit_stateful_investigation"

TOOL_ROUTES = {
    "calculate_customer_metrics": "profile",
    "get_campaign_eligibility": "profile",
    "get_customer_profile": "profile",
    "get_customer_events": "events",
    "get_purchase_history": "events",
    "search_knowledge_base": "knowledge",
}


class WorkflowExecutionError(AgentExecutionError):
    pass


class WorkflowSafetyError(WorkflowExecutionError):
    pass


class WorkflowState(TypedDict, total=False):
    request: dict[str, Any]
    resolved_customer_id: str
    input_items: list[dict[str, Any]]
    pending_calls: list[dict[str, Any]]
    tool_trace: list[dict[str, Any]]
    response_ids: list[str]
    token_totals: dict[str, int]
    model_rounds: int
    model: str
    answer: dict[str, Any]
    raw_output_text: str
    route: WorkflowRoute
    transitions: list[str]
    started_at: float
    recommendation: Literal["ANALYSIS_ONLY"]
    approval_required: bool
    action_executed: bool


class LangGraphCustomerInvestigator(CustomerInvestigator):
    """Commit 10's agent runtime orchestrated as an explicit state graph."""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        config: AgentConfig | None = None,
        responses_client: Any | None = None,
        checkpointer: InMemorySaver | None = None,
    ) -> None:
        super().__init__(
            registry,
            config=config,
            responses_client=responses_client,
        )
        self.checkpointer = checkpointer or InMemorySaver()
        self.graph = self._build_graph()
        self._resumes: dict[str, int] = {}

    def _build_graph(self):
        builder = StateGraph(WorkflowState)
        builder.add_node("interpret_request", self._interpret_request)
        builder.add_node("resolve_customer", self._resolve_customer)
        builder.add_node("investigation_router", self._investigation_router)
        builder.add_node("profile", self._profile)
        builder.add_node("events", self._events)
        builder.add_node("knowledge", self._knowledge)
        builder.add_node("reason_about_case", self._reason_about_case)
        builder.add_node("recommend_action", self._recommend_action)
        builder.add_node("approval_required", self._approval_required)
        builder.add_node("execute_action", self._execute_action)
        builder.add_node("finish", self._finish)

        builder.add_edge(START, "interpret_request")
        builder.add_edge("interpret_request", "resolve_customer")
        builder.add_edge("resolve_customer", "investigation_router")
        builder.add_conditional_edges(
            "investigation_router",
            self._route_investigation,
            {
                "profile": "profile",
                "events": "events",
                "knowledge": "knowledge",
                "reason_about_case": "reason_about_case",
                "recommend_action": "recommend_action",
            },
        )
        for node_name in ("profile", "events", "knowledge", "reason_about_case"):
            builder.add_edge(node_name, "investigation_router")
        builder.add_edge("recommend_action", "approval_required")
        builder.add_conditional_edges(
            "approval_required",
            self._route_approval,
            {"execute_action": "execute_action", "finish": "finish"},
        )
        builder.add_edge("execute_action", "finish")
        builder.add_edge("finish", END)
        return builder.compile(checkpointer=self.checkpointer)

    def investigate(
        self,
        customer_id: str,
        question: str,
        *,
        thread_id: str | None = None,
    ) -> WorkflowRun:
        return self.start(
            customer_id,
            question,
            thread_id=thread_id or f"signaldesk-{uuid4()}",
        )

    def start(
        self,
        customer_id: str,
        question: str,
        *,
        thread_id: str,
    ) -> WorkflowRun:
        request = InvestigationRequest(customer_id=customer_id, question=question)
        initial_state: WorkflowState = {
            "request": request.model_dump(mode="json"),
            "pending_calls": [],
            "tool_trace": [],
            "response_ids": [],
            "token_totals": self._empty_token_totals(),
            "model_rounds": 0,
            "transitions": [],
            "started_at": time.perf_counter(),
            "approval_required": False,
            "action_executed": False,
        }
        state = self.graph.invoke(initial_state, self._config(thread_id))
        return self._build_run(state, thread_id)

    def resume(self, thread_id: str) -> WorkflowRun:
        snapshot = self.graph.get_state(self._config(thread_id))
        if not snapshot.values:
            raise WorkflowExecutionError(f"No checkpoint exists for thread {thread_id}")
        self._resumes[thread_id] = self._resumes.get(thread_id, 0) + 1
        state = self.graph.invoke(None, self._config(thread_id))
        return self._build_run(state, thread_id)

    @staticmethod
    def _config(thread_id: str) -> dict[str, Any]:
        return {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": 64,
        }

    @staticmethod
    def _empty_token_totals() -> dict[str, int]:
        return {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
            "total_tokens": 0,
            "api_attempts": 0,
        }

    @staticmethod
    def _transition(state: WorkflowState, node_name: str) -> list[str]:
        return [*state.get("transitions", []), node_name]

    def _interpret_request(self, state: WorkflowState) -> dict[str, Any]:
        request = InvestigationRequest.model_validate(state["request"])
        return {
            "input_items": [{
                "role": "user",
                "content": [{
                    "type": "input_text",
                    "text": build_user_input(request),
                }],
            }],
            "transitions": self._transition(state, "interpret_request"),
        }

    def _resolve_customer(self, state: WorkflowState) -> dict[str, Any]:
        request = InvestigationRequest.model_validate(state["request"])
        return {
            "resolved_customer_id": request.customer_id,
            "transitions": self._transition(state, "resolve_customer"),
        }

    def _investigation_router(self, state: WorkflowState) -> dict[str, Any]:
        return {
            "route": self._next_route(state),
            "transitions": self._transition(state, "investigation_router"),
        }

    def _next_route(self, state: WorkflowState) -> WorkflowRoute:
        if state.get("answer") is not None:
            return "recommend_action"
        pending = state.get("pending_calls", [])
        if not pending:
            return "reason_about_case"
        tool_name = self._item_value(pending[0], "name")
        try:
            return TOOL_ROUTES[tool_name]  # type: ignore[return-value]
        except KeyError as exc:
            raise WorkflowExecutionError(
                f"Model requested a tool outside the workflow: {tool_name}"
            ) from exc

    @staticmethod
    def _route_investigation(state: WorkflowState) -> WorkflowRoute:
        return state["route"]

    def _profile(self, state: WorkflowState) -> dict[str, Any]:
        return self._execute_pending_tool(state, "profile")

    def _events(self, state: WorkflowState) -> dict[str, Any]:
        return self._execute_pending_tool(state, "events")

    def _knowledge(self, state: WorkflowState) -> dict[str, Any]:
        return self._execute_pending_tool(state, "knowledge")

    def _execute_pending_tool(
        self,
        state: WorkflowState,
        route_name: Literal["profile", "events", "knowledge"],
    ) -> dict[str, Any]:
        pending = state.get("pending_calls", [])
        if not pending:
            raise WorkflowExecutionError(f"{route_name} route has no pending tool call")
        function_call = pending[0]
        tool_name = self._item_value(function_call, "name")
        if TOOL_ROUTES.get(tool_name) != route_name:
            raise WorkflowExecutionError(
                f"Tool {tool_name} was incorrectly routed to {route_name}"
            )
        raw_arguments = self._item_value(function_call, "arguments")
        parsed_arguments = self._parse_arguments(raw_arguments)
        result = self._execute_bound_tool(
            state["resolved_customer_id"],
            tool_name,
            raw_arguments,
            parsed_arguments,
        )
        trace = ToolTrace(
            round_number=state["model_rounds"],
            call_id=self._item_value(function_call, "call_id"),
            tool_name=tool_name,
            arguments=parsed_arguments,
            success=result.success,
            error_code=result.error.code if result.error else None,
            latency_ms=result.latency_ms,
            output=result.output,
        )
        input_items = [
            *state["input_items"],
            {
                "type": "function_call_output",
                "call_id": trace.call_id,
                "output": result.model_dump_json(),
            },
        ]
        return {
            "pending_calls": pending[1:],
            "tool_trace": [*state.get("tool_trace", []), trace.model_dump(mode="json")],
            "input_items": input_items,
            "transitions": self._transition(state, route_name),
        }

    def _reason_about_case(self, state: WorkflowState) -> dict[str, Any]:
        round_number = state.get("model_rounds", 0) + 1
        if round_number > self.config.max_model_rounds:
            raise AgentLimitError("Agent exceeded max_model_rounds without a final answer")
        traces = state.get("tool_trace", [])

        def generate():
            return self._responses.create(
                model=self.config.model,
                instructions=SYSTEM_INSTRUCTIONS,
                input=state["input_items"],
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
                    "commit": "11",
                    "workflow_version": WORKFLOW_VERSION,
                },
            )

        response, attempts = with_exponential_backoff(
            generate,
            retryable_exceptions=self._retryable_errors,
            max_attempts=self.config.max_attempts,
        )
        if getattr(response, "status", None) != "completed":
            raise IncompleteAgentResponseError(
                f"Response {getattr(response, 'id', '<unknown>')} was not completed"
            )
        totals = dict(state["token_totals"])
        totals["api_attempts"] += attempts
        self._add_usage(totals, response)
        response_ids = [*state.get("response_ids", []), response.id]
        function_calls = [
            self._serialize_item(item)
            for item in response.output
            if self._item_value(item, "type") == "function_call"
        ]
        update: dict[str, Any] = {
            "model": getattr(response, "model", self.config.model),
            "model_rounds": round_number,
            "response_ids": response_ids,
            "token_totals": totals,
            "transitions": self._transition(state, "reason_about_case"),
        }
        if function_calls:
            if len(traces) + len(function_calls) > self.config.max_tool_calls:
                raise AgentLimitError("Agent exceeded max_tool_calls")
            update["input_items"] = [
                *state["input_items"],
                *(self._serialize_item(item) for item in response.output),
            ]
            update["pending_calls"] = function_calls
            return update

        raw_output_text = response.output_text
        try:
            answer = InvestigationAnswer.model_validate_json(raw_output_text)
        except ValidationError as exc:
            raise WorkflowExecutionError(
                "Final response failed local InvestigationAnswer validation"
            ) from exc
        update.update({
            "answer": answer.model_dump(mode="json"),
            "raw_output_text": raw_output_text,
            "pending_calls": [],
        })
        return update

    def _recommend_action(self, state: WorkflowState) -> dict[str, Any]:
        if state.get("answer") is None:
            raise WorkflowExecutionError("Cannot recommend a next step without an answer")
        return {
            "recommendation": "ANALYSIS_ONLY",
            "approval_required": False,
            "transitions": self._transition(state, "recommend_action"),
        }

    def _approval_required(self, state: WorkflowState) -> dict[str, Any]:
        return {"transitions": self._transition(state, "approval_required")}

    @staticmethod
    def _route_approval(
        state: WorkflowState,
    ) -> Literal["execute_action", "finish"]:
        return "execute_action" if state.get("approval_required") else "finish"

    def _execute_action(self, state: WorkflowState) -> dict[str, Any]:
        raise WorkflowSafetyError(
            "Commit 11 is analysis-only; action execution starts in Commit 12"
        )

    def _finish(self, state: WorkflowState) -> dict[str, Any]:
        return {
            "action_executed": False,
            "transitions": self._transition(state, "finish"),
        }

    def _build_run(self, state: WorkflowState, thread_id: str) -> WorkflowRun:
        try:
            request = InvestigationRequest.model_validate(state["request"])
            answer = InvestigationAnswer.model_validate(state["answer"])
            traces = [ToolTrace.model_validate(item) for item in state["tool_trace"]]
        except (KeyError, ValidationError) as exc:
            raise WorkflowExecutionError("Workflow ended without a valid result") from exc
        totals = state["token_totals"]
        model_rounds = state["model_rounds"]
        metrics = AgentRunMetrics(
            model=state.get("model", self.config.model),
            prompt_version=PROMPT_VERSION,
            reasoning_effort="none",
            response_ids=state["response_ids"],
            model_rounds=model_rounds,
            tool_calls=len(traces),
            api_requests=model_rounds,
            api_attempts=totals["api_attempts"],
            api_retry_attempts=totals["api_attempts"] - model_rounds,
            input_tokens=totals["input_tokens"],
            cached_input_tokens=totals["cached_input_tokens"],
            output_tokens=totals["output_tokens"],
            reasoning_tokens=totals["reasoning_tokens"],
            total_tokens=totals["total_tokens"],
            latency_seconds=round(time.perf_counter() - state["started_at"], 4),
            estimated_cost_usd=estimate_text_cost_usd(
                self.config.model,
                totals["input_tokens"],
                totals["cached_input_tokens"],
                totals["output_tokens"],
            ),
        )
        transitions = state["transitions"]
        checkpoint_count = sum(
            1 for _ in self.checkpointer.list(self._config(thread_id))
        )
        return WorkflowRun(
            request=request,
            answer=answer,
            tool_trace=traces,
            metrics=metrics,
            raw_output_text=state["raw_output_text"],
            workflow=WorkflowMetrics(
                workflow_version=WORKFLOW_VERSION,
                thread_id=thread_id,
                transitions=transitions,
                routed_tool_nodes=[
                    node for node in transitions if node in {"profile", "events", "knowledge"}
                ],
                checkpoint_count=checkpoint_count,
                resume_count=self._resumes.get(thread_id, 0),
                recommendation=state["recommendation"],
                approval_required=state["approval_required"],
                action_executed=state["action_executed"],
            ),
        )
