from __future__ import annotations

from typing import Literal

from pydantic import Field

from src.agent.schemas import InvestigationRun, StrictModel


WorkflowRoute = Literal[
    "profile",
    "events",
    "knowledge",
    "reason_about_case",
    "recommend_action",
]


class WorkflowMetrics(StrictModel):
    workflow_version: str
    thread_id: str
    transitions: list[str]
    routed_tool_nodes: list[Literal["profile", "events", "knowledge"]]
    checkpoint_count: int = Field(ge=1)
    resume_count: int = Field(ge=0)
    recommendation: Literal["ANALYSIS_ONLY"]
    approval_required: bool
    action_executed: bool


class WorkflowRun(InvestigationRun):
    workflow: WorkflowMetrics
