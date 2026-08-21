from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from src.actions import ActionProposal, ApprovalDecision, HumanApprovalWorkflow
from src.actions.schemas import SupportCaseAction
from src.agent.investigator import AgentConfig
from src.agent.prompts import PROMPT_VERSION
from src.observability import (
    EvaluationUpdate,
    ObservabilityStore,
    ObservabilitySummary,
    ObservedError,
    ObservedTokenUsage,
    ObservedToolCall,
    RunObservation,
    RunObservationList,
)
from src.tools import CDPTools, ToolRegistry
from src.tools.schemas import ToolCallResult
from src.workflow import LangGraphCustomerInvestigator
from src.workflow.schemas import WorkflowRun

from .config import APIConfig
from .schemas import (
    ActionPackageView,
    Customer360View,
    CustomerSearchItem,
    CustomerSearchView,
    DraftSupportActionRequest,
    InvestigationCreateRequest,
    InvestigationMetricsView,
    InvestigationView,
    SourceView,
    ToolExecutionView,
)
from .store import InvestigationStore


class CustomerNotFound(KeyError):
    pass


class InvestigationUnavailable(RuntimeError):
    pass


class CustomerRepository:
    def __init__(self, database: str | Path) -> None:
        try:
            import duckdb
        except ImportError as exc:
            raise RuntimeError("Install DuckDB from requirements-commit16.txt") from exc
        self._connection = duckdb.connect(str(database), read_only=True)
        self._lock = threading.RLock()

    def close(self) -> None:
        self._connection.close()

    def search(self, query: str, limit: int) -> CustomerSearchView:
        normalized = query.strip()
        pattern = f"%{normalized}%"
        where = ""
        params: list[Any] = []
        if normalized:
            where = (
                "WHERE customer_id ILIKE ? OR customer_status ILIKE ? "
                "OR loyalty_tier ILIKE ? OR country ILIKE ?"
            )
            params = [pattern] * 4
        sql = f"""
            SELECT customer_id, customer_status, loyalty_tier, country,
                   days_since_last_seen, purchase_decline_flag,
                   engagement_decline_flag, support_attention_flag,
                   CAST(purchase_decline_flag AS INTEGER)
                     + CAST(engagement_decline_flag AS INTEGER)
                     + CAST(support_attention_flag AS INTEGER) AS warning_count
            FROM customer_360
            {where}
            ORDER BY warning_count DESC, days_since_last_seen DESC, customer_id
            LIMIT ?
        """
        with self._lock:
            rows = self._connection.execute(sql, [*params, limit]).fetchall()
        customers = [
            CustomerSearchItem(
                customer_id=row[0],
                customer_status=row[1],
                loyalty_tier=row[2],
                country=row[3],
                days_since_last_seen=row[4],
                purchase_decline_flag=row[5],
                engagement_decline_flag=row[6],
                support_attention_flag=row[7],
                warning_count=row[8],
            )
            for row in rows
        ]
        return CustomerSearchView(
            query=normalized,
            returned_count=len(customers),
            customers=customers,
        )


class SignalDeskService:
    def __init__(
        self,
        config: APIConfig,
        *,
        investigator_factory: Callable[[ToolRegistry], Any] | None = None,
    ) -> None:
        self.config = config
        self._customers = CustomerRepository(config.database)
        self._cdp_tools = CDPTools(config.database, corpus_dir=config.corpus_dir)
        self._registry = ToolRegistry(self._cdp_tools)
        self._investigation_store = InvestigationStore(
            config.runtime_dir / "investigations.sqlite3"
        )
        self._observability = ObservabilityStore(
            config.runtime_dir / "observability.sqlite3"
        )
        self._actions = HumanApprovalWorkflow(config.runtime_dir / "actions")
        self._investigator_factory = investigator_factory or self._default_investigator
        self._investigator: Any | None = None
        self._investigation_lock = threading.RLock()
        self._tool_lock = threading.RLock()
        self._action_lock = threading.RLock()

    @staticmethod
    def _default_investigator(registry: ToolRegistry) -> LangGraphCustomerInvestigator:
        return LangGraphCustomerInvestigator(
            registry,
            config=AgentConfig(model="gpt-5.6-luna", reasoning_effort="none"),
        )

    def close(self) -> None:
        self._actions.close()
        self._observability.close()
        self._investigation_store.close()
        self._cdp_tools.close()
        self._customers.close()

    def search_customers(self, query: str, limit: int) -> CustomerSearchView:
        return self._customers.search(query, limit)

    def customer_360(self, customer_id: str) -> Customer360View:
        with self._tool_lock:
            profile = self._require_output(
                self._registry.execute(
                    "get_customer_profile",
                    {"customer_id": customer_id},
                )
            )
            metrics = self._require_output(
                self._registry.execute(
                    "calculate_customer_metrics",
                    {"customer_id": customer_id},
                )
            )
            campaign = self._require_output(
                self._registry.execute(
                    "get_campaign_eligibility",
                    {"customer_id": customer_id},
                )
            )
        support = bool(metrics["support"]["support_attention_flag"])
        purchase = bool(metrics["purchase"]["purchase_decline_flag"])
        engagement = bool(metrics["engagement"]["engagement_decline_flag"])
        return Customer360View(
            customer_id=customer_id,
            profile=profile,
            metrics=metrics,
            campaign_eligibility=campaign,
            warning_count=sum((purchase, engagement, support)),
        )

    @staticmethod
    def _require_output(result: ToolCallResult) -> dict[str, Any]:
        if result.success and result.output is not None:
            return result.output
        if result.error and result.error.code == "NOT_FOUND":
            raise CustomerNotFound(result.error.message)
        message = result.error.message if result.error else "Tool failed"
        raise RuntimeError(message)

    def investigate(
        self,
        user_id: str,
        request: InvestigationCreateRequest,
        request_id: str,
    ) -> InvestigationView:
        started_at = datetime.now(UTC)
        started = time.perf_counter()
        stage = "initialize_agent"
        with self._investigation_lock:
            if self._investigator is None:
                try:
                    self._investigator = self._investigator_factory(self._registry)
                except Exception as exc:
                    self._record_failed_run(
                        request_id,
                        user_id,
                        request,
                        stage,
                        exc,
                        started_at,
                        started,
                    )
                    raise InvestigationUnavailable(
                        "Live investigation is unavailable. Confirm OPENAI_API_KEY and "
                        "the Commit 16 dependencies."
                    ) from exc
            stage = "agent_investigation"
            try:
                run = self._investigator.investigate(
                    request.customer_id,
                    request.question,
                )
            except Exception as exc:
                self._record_failed_run(
                    request_id,
                    user_id,
                    request,
                    stage,
                    exc,
                    started_at,
                    started,
                )
                raise InvestigationUnavailable(
                    "The investigation workflow did not complete."
                ) from exc
        view = self._to_investigation_view(run, request_id)
        self._observability.record(
            self._to_run_observation(
                request_id,
                user_id,
                run,
                view,
                started_at,
            )
        )
        self._investigation_store.save(user_id, view)
        return view

    def get_investigation(
        self,
        user_id: str,
        investigation_id: str,
    ) -> InvestigationView:
        return self._investigation_store.get(user_id, investigation_id)

    @staticmethod
    def _to_investigation_view(
        run: WorkflowRun,
        request_id: str,
    ) -> InvestigationView:
        investigation_id = f"INV-{uuid4().hex[:20]}"
        cited = set(run.answer.policy_document_ids)
        sources: dict[str, SourceView] = {}
        tools: list[ToolExecutionView] = []
        for trace in run.tool_trace:
            output = trace.output or {}
            tools.append(
                ToolExecutionView(
                    round_number=trace.round_number,
                    tool_name=trace.tool_name,
                    arguments=trace.arguments,
                    success=trace.success,
                    error_code=trace.error_code,
                    latency_ms=trace.latency_ms,
                    result_summary=SignalDeskService._summarize_tool(
                        trace.tool_name,
                        output,
                    ),
                )
            )
            if trace.tool_name == "search_knowledge_base":
                for item in output.get("results", []):
                    sources[item["document_id"]] = SourceView(
                        document_id=item["document_id"],
                        title=item["title"],
                        family=item["family"],
                        excerpt=item["excerpt"],
                        score=item["score"],
                        cited=item["document_id"] in cited,
                    )
        return InvestigationView(
            request_id=request_id,
            investigation_id=investigation_id,
            customer_id=run.request.customer_id,
            question=run.request.question,
            task_status=run.answer.task_status,
            conclusion_code=run.answer.conclusion_code,
            risk_level=run.answer.risk_level,
            summary=run.answer.summary,
            evidence=run.answer.evidence,
            limitations=run.answer.limitations,
            policy_document_ids=run.answer.policy_document_ids,
            tools=tools,
            sources=list(sources.values()),
            timeline=run.workflow.transitions,
            metrics=InvestigationMetricsView(
                model=run.metrics.model,
                prompt_version=run.metrics.prompt_version,
                reasoning_effort="none",
                tool_calls=run.metrics.tool_calls,
                model_rounds=run.metrics.model_rounds,
                latency_seconds=run.metrics.latency_seconds,
                total_tokens=run.metrics.total_tokens,
                estimated_cost_usd=run.metrics.estimated_cost_usd,
            ),
            created_at=datetime.now(UTC).isoformat(),
        )

    @staticmethod
    def _to_run_observation(
        request_id: str,
        user_id: str,
        run: WorkflowRun,
        view: InvestigationView,
        started_at: datetime,
    ) -> RunObservation:
        tool_calls: list[ObservedToolCall] = []
        documents: list[str] = []
        scores: list[float] = []
        errors: list[ObservedError] = []
        for trace in run.tool_trace:
            output = trace.output or {}
            returned_count = output.get("returned_count")
            tool_calls.append(
                ObservedToolCall(
                    round_number=trace.round_number,
                    tool_name=trace.tool_name,
                    success=trace.success,
                    error_code=trace.error_code,
                    latency_ms=trace.latency_ms,
                    returned_count=(
                        returned_count if isinstance(returned_count, int) else None
                    ),
                )
            )
            if not trace.success:
                errors.append(
                    ObservedError(
                        stage=f"tool:{trace.tool_name}",
                        error_type=trace.error_code or "TOOL_ERROR",
                        message="The tool call returned a structured failure.",
                    )
                )
            if trace.tool_name == "search_knowledge_base" and trace.success:
                for item in output.get("results", []):
                    documents.append(str(item["document_id"]))
                    scores.append(float(item["score"]))
        metrics = run.metrics
        return RunObservation(
            request_id=request_id,
            investigation_id=view.investigation_id,
            user_id=user_id,
            customer_id=run.request.customer_id,
            question=run.request.question,
            status="SUCCESS",
            task_success=run.answer.task_status == "COMPLETED",
            model=metrics.model,
            prompt_version=metrics.prompt_version,
            reasoning_effort="none",
            tool_calls=tool_calls,
            retrieval_documents=documents,
            retrieval_scores=scores,
            tokens=ObservedTokenUsage(
                input=metrics.input_tokens,
                cached_input=metrics.cached_input_tokens,
                output=metrics.output_tokens,
                reasoning=metrics.reasoning_tokens,
                total=metrics.total_tokens,
            ),
            cost_usd=metrics.estimated_cost_usd,
            latency_seconds=metrics.latency_seconds,
            final_answer=run.answer.model_dump(mode="json"),
            errors=errors,
            started_at=started_at.isoformat(),
            completed_at=datetime.now(UTC).isoformat(),
        )

    def _record_failed_run(
        self,
        request_id: str,
        user_id: str,
        request: InvestigationCreateRequest,
        stage: str,
        error: Exception,
        started_at: datetime,
        started: float,
    ) -> None:
        message = str(error).strip() or error.__class__.__name__
        self._observability.record(
            RunObservation(
                request_id=request_id,
                investigation_id=None,
                user_id=user_id,
                customer_id=request.customer_id,
                question=request.question,
                status="ERROR",
                task_success=False,
                model="gpt-5.6-luna",
                prompt_version=PROMPT_VERSION,
                reasoning_effort="none",
                tool_calls=[],
                retrieval_documents=[],
                retrieval_scores=[],
                tokens=ObservedTokenUsage(
                    input=0,
                    cached_input=0,
                    output=0,
                    reasoning=0,
                    total=0,
                ),
                cost_usd=None,
                latency_seconds=round(time.perf_counter() - started, 4),
                final_answer=None,
                errors=[
                    ObservedError(
                        stage=stage,
                        error_type=error.__class__.__name__,
                        message=message[:500],
                    )
                ],
                started_at=started_at.isoformat(),
                completed_at=datetime.now(UTC).isoformat(),
            )
        )

    def observability_summary(self, user_id: str) -> ObservabilitySummary:
        return self._observability.summary_for_user(user_id)

    def observability_runs(
        self,
        user_id: str,
        limit: int,
    ) -> RunObservationList:
        return self._observability.list_for_user(user_id, limit)

    def observability_run(
        self,
        user_id: str,
        request_id: str,
    ) -> RunObservation:
        return self._observability.get(user_id, request_id)

    def evaluate_run(
        self,
        user_id: str,
        request_id: str,
        update: EvaluationUpdate,
    ) -> RunObservation:
        return self._observability.update_evaluation(
            user_id,
            request_id,
            update.result,
            update.note,
        )

    @staticmethod
    def _summarize_tool(tool_name: str, output: dict[str, Any]) -> str:
        if not output:
            return "No structured output"
        if tool_name == "search_knowledge_base":
            return f"{output.get('returned_count', 0)} policy documents retrieved"
        if tool_name == "get_customer_events":
            return (
                f"{output.get('returned_count', 0)} of "
                f"{output.get('total_count', 0)} events returned"
            )
        if tool_name == "get_purchase_history":
            return (
                f"{output.get('returned_count', 0)} of "
                f"{output.get('total_count', 0)} orders returned"
            )
        if tool_name == "get_campaign_eligibility":
            return f"Campaign status: {output.get('status', 'unknown')}"
        if tool_name == "calculate_customer_metrics":
            return "Customer 360 metrics returned"
        if tool_name == "get_customer_profile":
            return "PII-safe profile returned"
        return "Structured result returned"

    def draft_support_action(
        self,
        user_id: str,
        reviewer_id: str,
        investigation_id: str,
        request: DraftSupportActionRequest,
    ) -> ActionPackageView:
        investigation = self._investigation_store.get(user_id, investigation_id)
        action = SupportCaseAction(
            priority=request.priority,
            summary=(
                f"Review {investigation.investigation_id}: {investigation.summary}"
            )[:500],
        )
        proposal = ActionProposal.build(
            customer_id=investigation.customer_id,
            action=action,
            recommendation="Open a synthetic support case for analyst follow-up.",
            reason=(
                f"Workspace analyst {reviewer_id} requested a reviewed follow-up. "
                f"Analyst reason: {request.reason}"
            ),
            expected_impact=(
                "A synthetic support-case event is written only after exact-payload "
                "human approval."
            ),
            source_case_id=investigation.investigation_id,
            proposed_by="signaldesk_workspace",
        )
        self._investigation_store.link_action(
            user_id,
            investigation_id,
            proposal,
        )
        with self._action_lock:
            run = self._actions.start(proposal)
        return ActionPackageView(
            investigation_id=investigation_id,
            proposal=proposal,
            run=run,
        )

    def decide_action(
        self,
        user_id: str,
        reviewer_id: str,
        action_id: str,
        decision: str,
        reason: str,
    ) -> ActionPackageView:
        investigation_id, proposal = self._investigation_store.get_action(
            user_id,
            action_id,
        )
        with self._action_lock:
            run = self._actions.decide(
                action_id,
                ApprovalDecision(
                    action_id=action_id,
                    decision=decision,
                    reviewer_id=reviewer_id,
                    reason=reason,
                ),
            )
        return ActionPackageView(
            investigation_id=investigation_id,
            proposal=proposal,
            run=run,
        )
