from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from .schemas import ActionProposal, ActionRun, ApprovalDecision, ApprovalRequest
from .store import ActionStore


WORKFLOW_VERSION = "commit12_v1_durable_human_approval"


class ApprovalWorkflowError(RuntimeError):
    pass


class ApprovalWorkflowState(TypedDict, total=False):
    proposal: dict[str, Any]
    decision: dict[str, Any]
    synthetic_event_id: str
    transitions: list[str]


class HumanApprovalWorkflow:
    """Durable approval boundary for consequential synthetic actions."""

    def __init__(
        self,
        runtime_dir: str | Path = "data/runtime/commit12",
        *,
        fail_after_event_action_ids: set[str] | None = None,
    ) -> None:
        os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")
        self.runtime_dir = Path(runtime_dir)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self._checkpoint_connection = sqlite3.connect(
            self.runtime_dir / "checkpoints.sqlite3",
            check_same_thread=False,
        )
        self.checkpointer = SqliteSaver(self._checkpoint_connection)
        self.store = ActionStore(self.runtime_dir / "actions.sqlite3")
        self.fail_after_event_action_ids = fail_after_event_action_ids or set()
        self.graph = self._build_graph()

    def close(self) -> None:
        self.store.close()
        self._checkpoint_connection.close()

    def __enter__(self) -> "HumanApprovalWorkflow":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _build_graph(self):
        builder = StateGraph(ApprovalWorkflowState)
        builder.add_node("validate_proposal", self._validate_proposal)
        builder.add_node("record_proposal", self._record_proposal)
        builder.add_node("record_approval_request", self._record_approval_request)
        builder.add_node("await_approval", self._await_approval)
        builder.add_node("record_decision", self._record_decision)
        builder.add_node("execute_action", self._execute_action)
        builder.add_node("finish", self._finish)

        builder.add_edge(START, "validate_proposal")
        builder.add_edge("validate_proposal", "record_proposal")
        builder.add_edge("record_proposal", "record_approval_request")
        builder.add_edge("record_approval_request", "await_approval")
        builder.add_edge("await_approval", "record_decision")
        builder.add_conditional_edges(
            "record_decision",
            self._route_decision,
            {"execute_action": "execute_action", "finish": "finish"},
        )
        builder.add_edge("execute_action", "finish")
        builder.add_edge("finish", END)
        return builder.compile(checkpointer=self.checkpointer)

    def start(
        self,
        proposal: ActionProposal,
        *,
        thread_id: str | None = None,
    ) -> ActionRun:
        thread_id = thread_id or proposal.action_id
        existing = self.graph.get_state(self._config(thread_id))
        if existing.values:
            existing_id = existing.values.get("proposal", {}).get("action_id")
            if existing_id != proposal.action_id:
                raise ApprovalWorkflowError(
                    f"Thread {thread_id} already belongs to action {existing_id}"
                )
            if existing.next == ("execute_action",):
                raise ApprovalWorkflowError(
                    f"Action {proposal.action_id} has an interrupted execution; "
                    "call recover"
                )
            return self._build_run(existing.values, thread_id)
        state = self.graph.invoke(
            {
                "proposal": proposal.model_dump(mode="json"),
                "transitions": [],
            },
            self._config(thread_id),
        )
        return self._build_run(state, thread_id)

    def decide(
        self,
        thread_id: str,
        decision: ApprovalDecision,
    ) -> ActionRun:
        snapshot = self._require_state(thread_id)
        proposal = ActionProposal.model_validate(snapshot.values["proposal"])
        if decision.action_id != proposal.action_id:
            raise ApprovalWorkflowError("decision action_id does not match thread")
        if snapshot.next != ("await_approval",):
            raise ApprovalWorkflowError(
                f"Action {proposal.action_id} is not waiting for approval"
            )
        state = self.graph.invoke(
            Command(resume=decision.model_dump(mode="json")),
            self._config(thread_id),
        )
        return self._build_run(state, thread_id)

    def recover(self, thread_id: str) -> ActionRun:
        snapshot = self._require_state(thread_id)
        if snapshot.next != ("execute_action",):
            raise ApprovalWorkflowError(
                f"Thread {thread_id} has no interrupted execution to recover"
            )
        state = self.graph.invoke(None, self._config(thread_id))
        return self._build_run(state, thread_id)

    @staticmethod
    def _config(thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}}

    @staticmethod
    def _transition(
        state: ApprovalWorkflowState,
        node_name: str,
    ) -> list[str]:
        return [*state.get("transitions", []), node_name]

    def _validate_proposal(self, state: ApprovalWorkflowState) -> dict[str, Any]:
        proposal = ActionProposal.model_validate(state["proposal"])
        return {
            "proposal": proposal.model_dump(mode="json"),
            "transitions": self._transition(state, "validate_proposal"),
        }

    def _record_proposal(self, state: ApprovalWorkflowState) -> dict[str, Any]:
        self.store.record_proposal(ActionProposal.model_validate(state["proposal"]))
        return {"transitions": self._transition(state, "record_proposal")}

    def _record_approval_request(
        self,
        state: ApprovalWorkflowState,
    ) -> dict[str, Any]:
        self.store.record_approval_request(
            ActionProposal.model_validate(state["proposal"])
        )
        return {
            "transitions": self._transition(state, "record_approval_request")
        }

    def _await_approval(self, state: ApprovalWorkflowState) -> dict[str, Any]:
        proposal = ActionProposal.model_validate(state["proposal"])
        resumed_value = interrupt(self._approval_request(proposal).model_dump(mode="json"))
        decision = ApprovalDecision.model_validate(resumed_value)
        if decision.action_id != proposal.action_id:
            raise ApprovalWorkflowError("approval applies to a different action")
        return {
            "decision": decision.model_dump(mode="json"),
            "transitions": self._transition(state, "await_approval"),
        }

    def _record_decision(self, state: ApprovalWorkflowState) -> dict[str, Any]:
        proposal = ActionProposal.model_validate(state["proposal"])
        decision = ApprovalDecision.model_validate(state["decision"])
        self.store.record_decision(proposal, decision)
        return {"transitions": self._transition(state, "record_decision")}

    @staticmethod
    def _route_decision(state: ApprovalWorkflowState) -> str:
        decision = ApprovalDecision.model_validate(state["decision"])
        return "execute_action" if decision.decision == "APPROVED" else "finish"

    def _execute_action(self, state: ApprovalWorkflowState) -> dict[str, Any]:
        proposal = ActionProposal.model_validate(state["proposal"])
        event_id, _ = self.store.execute_approved(proposal)
        if proposal.action_id in self.fail_after_event_action_ids:
            raise RuntimeError("injected failure after synthetic event commit")
        return {
            "synthetic_event_id": event_id,
            "transitions": self._transition(state, "execute_action"),
        }

    def _finish(self, state: ApprovalWorkflowState) -> dict[str, Any]:
        return {"transitions": self._transition(state, "finish")}

    def _require_state(self, thread_id: str):
        snapshot = self.graph.get_state(self._config(thread_id))
        if not snapshot.values:
            raise ApprovalWorkflowError(f"No checkpoint exists for thread {thread_id}")
        return snapshot

    @staticmethod
    def _approval_request(proposal: ActionProposal) -> ApprovalRequest:
        return ApprovalRequest(
            action_id=proposal.action_id,
            customer_id=proposal.customer_id,
            action=proposal.action,
            recommendation=proposal.recommendation,
            reason=proposal.reason,
            expected_impact=proposal.expected_impact,
        )

    def _build_run(
        self,
        state: dict[str, Any],
        thread_id: str,
    ) -> ActionRun:
        proposal = ActionProposal.model_validate(state["proposal"])
        raw_decision = state.get("decision")
        decision = (
            ApprovalDecision.model_validate(raw_decision)
            if raw_decision is not None
            else None
        )
        event_id = state.get("synthetic_event_id")
        if decision is None:
            status = "PENDING_APPROVAL"
        elif decision.decision == "REJECTED":
            status = "REJECTED"
        else:
            status = "EXECUTED"
        return ActionRun(
            workflow_version=WORKFLOW_VERSION,
            thread_id=thread_id,
            action_id=proposal.action_id,
            status=status,
            approval_request=(
                self._approval_request(proposal) if decision is None else None
            ),
            decision=decision,
            synthetic_event_id=event_id,
            transitions=state.get("transitions", []),
        )
