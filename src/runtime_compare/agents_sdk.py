from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents import (
    Agent,
    Model,
    ModelSettings,
    RunConfig,
    RunContextWrapper,
    Runner,
    RunState,
    function_tool,
)

from src.actions import ActionProposal, ActionRun, ApprovalDecision, ApprovalRequest
from src.actions.schemas import CouponAction
from src.actions.store import ActionStore


AGENTS_SDK_WORKFLOW_VERSION = "commit13_v1_agents_sdk_coupon_approval"
TOOL_NAME = "issue_coupon"


class AgentsSDKWorkflowError(RuntimeError):
    pass


class AgentsSDKApprovalWorkflow:
    """OpenAI Agents SDK implementation of the Commit 12 approval contract."""

    def __init__(
        self,
        proposal: ActionProposal,
        runtime_dir: str | Path,
        *,
        model: str | Model = "gpt-5.6-luna",
        fail_after_event: bool = False,
    ) -> None:
        if not isinstance(proposal.action, CouponAction):
            raise AgentsSDKWorkflowError("comparison supports ISSUE_COUPON only")
        self.proposal = proposal
        self.runtime_dir = Path(runtime_dir)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.store_path = self.runtime_dir / "actions.sqlite3"
        self.state_path = self.runtime_dir / "run_state.json"
        self.decision_path = self.runtime_dir / "decision.json"
        self.result_path = self.runtime_dir / "result.json"
        self.model = model
        self.fail_after_event = fail_after_event
        self.agent = self._build_agent()
        self.run_config = RunConfig(
            tracing_disabled=True,
            workflow_name="SignalDesk Commit 13 coupon approval",
        )

    async def start(self) -> ActionRun:
        if self.result_path.exists():
            return self._read_result()
        if self.state_path.exists():
            return self._pending_run()

        with ActionStore(self.store_path) as store:
            store.record_proposal(self.proposal)
            store.record_approval_request(self.proposal)

        result = await Runner.run(
            self.agent,
            self._model_input(),
            context=self._context(),
            run_config=self.run_config,
        )
        self._validate_interruptions(result.interruptions)
        self._write_json(
            self.state_path,
            result.to_state().to_json(strict_context=True),
        )
        return self._pending_run()

    async def decide(self, decision: ApprovalDecision) -> ActionRun:
        if self.result_path.exists():
            raise AgentsSDKWorkflowError("action already has a final result")
        state = await self._load_state()
        interruption = self._validate_interruptions(state.get_interruptions())[0]
        if decision.action_id != self.proposal.action_id:
            raise AgentsSDKWorkflowError("decision action_id does not match proposal")

        if decision.decision == "APPROVED":
            state.approve(interruption)
        else:
            state.reject(
                interruption,
                rejection_message="The human reviewer rejected this exact action.",
            )
        # Persist the human input and SDK approval before any side effect can run.
        self._write_json(self.decision_path, decision.model_dump(mode="json"))
        self._write_json(self.state_path, state.to_json(strict_context=True))
        with ActionStore(self.store_path) as store:
            store.record_decision(self.proposal, decision)
        result = await Runner.run(
            self.agent,
            state,
            run_config=self.run_config,
        )
        if result.interruptions:
            raise AgentsSDKWorkflowError("unexpected second approval interruption")
        return self._finish(decision)

    async def recover(self) -> ActionRun:
        if self.result_path.exists():
            return self._read_result()
        if not self.decision_path.exists():
            raise AgentsSDKWorkflowError("no approved interrupted execution to recover")
        decision = ApprovalDecision.model_validate_json(
            self.decision_path.read_text(encoding="utf-8")
        )
        if decision.decision != "APPROVED":
            raise AgentsSDKWorkflowError("no approved interrupted execution to recover")
        state = await self._load_state()
        interruption = self._validate_interruptions(state.get_interruptions())[0]
        state.approve(interruption)
        self._write_json(self.state_path, state.to_json(strict_context=True))
        with ActionStore(self.store_path) as store:
            store.record_decision(self.proposal, decision)
        result = await Runner.run(
            self.agent,
            state,
            run_config=self.run_config,
        )
        if result.interruptions:
            raise AgentsSDKWorkflowError("recovery returned to approval interruption")
        return self._finish(decision)

    def pending_state_bytes(self) -> int:
        return self.state_path.stat().st_size

    def _build_agent(self) -> Agent[dict[str, Any]]:
        proposal = self.proposal

        async def issue_coupon(
            ctx: RunContextWrapper[dict[str, Any]],
            action_id: str,
            customer_id: str,
            coupon_code: str,
            discount_percent: int,
            expires_in_days: int,
        ) -> str:
            actual = {
                "action_id": action_id,
                "coupon_code": coupon_code,
                "customer_id": customer_id,
                "discount_percent": discount_percent,
                "expires_in_days": expires_in_days,
            }
            if actual != self._expected_tool_arguments():
                raise AgentsSDKWorkflowError(
                    "tool arguments differ from the reviewed proposal"
                )
            with ActionStore(ctx.context["store_path"]) as store:
                event_id, _ = store.execute_approved(proposal)
            if ctx.context.get("fail_after_event"):
                raise RuntimeError("injected failure after synthetic event commit")
            return json.dumps({"synthetic_event_id": event_id}, sort_keys=True)

        tool = function_tool(
            issue_coupon,
            name_override=TOOL_NAME,
            description_override="Issue the exact coupon proposed for this customer.",
            needs_approval=True,
            failure_error_function=None,
        )
        return Agent(
            name="SignalDesk coupon approval agent",
            instructions=(
                "Call issue_coupon exactly once with the supplied immutable proposal. "
                "Never alter its arguments."
            ),
            model=self.model,
            model_settings=ModelSettings(reasoning={"effort": "none"}),
            tools=[tool],
        )

    async def _load_state(self) -> RunState[Any, Agent[Any]]:
        if not self.state_path.exists():
            raise AgentsSDKWorkflowError("no serialized run state exists")
        return await RunState.from_json(
            self.agent,
            json.loads(self.state_path.read_text(encoding="utf-8")),
            context_override=self._context(),
            strict_context=True,
        )

    def _context(self) -> dict[str, Any]:
        return {
            "store_path": str(self.store_path),
            "fail_after_event": self.fail_after_event,
        }

    def _model_input(self) -> str:
        return json.dumps(
            {
                "instruction": "Submit this exact proposal for approval.",
                "proposal": self.proposal.model_dump(mode="json"),
            },
            sort_keys=True,
        )

    def _expected_tool_arguments(self) -> dict[str, Any]:
        action = self.proposal.action
        return {
            "action_id": self.proposal.action_id,
            "coupon_code": action.coupon_code,
            "customer_id": self.proposal.customer_id,
            "discount_percent": action.discount_percent,
            "expires_in_days": action.expires_in_days,
        }

    def _validate_interruptions(self, interruptions: list[Any]) -> list[Any]:
        if len(interruptions) != 1:
            raise AgentsSDKWorkflowError(
                f"expected one approval interruption, found {len(interruptions)}"
            )
        interruption = interruptions[0]
        if interruption.name != TOOL_NAME:
            raise AgentsSDKWorkflowError(
                f"unexpected approval tool: {interruption.name}"
            )
        try:
            arguments = json.loads(interruption.arguments)
        except (TypeError, json.JSONDecodeError) as exc:
            raise AgentsSDKWorkflowError("approval arguments are not valid JSON") from exc
        if arguments != self._expected_tool_arguments():
            raise AgentsSDKWorkflowError(
                "approval arguments differ from the immutable proposal"
            )
        return interruptions

    def _pending_run(self) -> ActionRun:
        return ActionRun(
            workflow_version=AGENTS_SDK_WORKFLOW_VERSION,
            thread_id=self.proposal.action_id,
            action_id=self.proposal.action_id,
            status="PENDING_APPROVAL",
            approval_request=self._approval_request(),
            transitions=["model_proposed_tool", "approval_interrupted"],
        )

    def _finish(self, decision: ApprovalDecision) -> ActionRun:
        with ActionStore(self.store_path) as store:
            event_id = (
                f"EVT-{self.proposal.action_id.removeprefix('ACT-')}"
                if store.event_count(self.proposal.action_id) == 1
                else None
            )
        if decision.decision == "APPROVED" and event_id is None:
            raise AgentsSDKWorkflowError("approved action produced no synthetic event")
        if decision.decision == "REJECTED" and event_id is not None:
            raise AgentsSDKWorkflowError("rejected action produced a synthetic event")
        run = ActionRun(
            workflow_version=AGENTS_SDK_WORKFLOW_VERSION,
            thread_id=self.proposal.action_id,
            action_id=self.proposal.action_id,
            status="EXECUTED" if event_id else "REJECTED",
            decision=decision,
            synthetic_event_id=event_id,
            transitions=[
                "model_proposed_tool",
                "approval_interrupted",
                "decision_recorded",
                *(["tool_executed"] if event_id else []),
                "finished",
            ],
        )
        self._write_json(self.result_path, run.model_dump(mode="json"))
        return run

    def _read_result(self) -> ActionRun:
        run = ActionRun.model_validate_json(
            self.result_path.read_text(encoding="utf-8")
        )
        if run.action_id != self.proposal.action_id:
            raise AgentsSDKWorkflowError("stored result belongs to another action")
        return run

    def _approval_request(self) -> ApprovalRequest:
        return ApprovalRequest(
            action_id=self.proposal.action_id,
            customer_id=self.proposal.customer_id,
            action=self.proposal.action,
            recommendation=self.proposal.recommendation,
            reason=self.proposal.reason,
            expected_impact=self.proposal.expected_impact,
        )

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        temporary.replace(path)
