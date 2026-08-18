from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import agents
from openai.types.responses import ResponseFunctionToolCall

from evals.commit12.make_cases import read_jsonl
from evals.commit13.make_cases import build_cases, validate_cases
from evals.commit13.replay_model import FrozenCouponToolCallModel
from src.actions import ActionProposal, ApprovalDecision
from src.actions.store import ActionStore
from src.runtime_compare import (
    AGENTS_SDK_WORKFLOW_VERSION,
    AgentsSDKApprovalWorkflow,
    AgentsSDKWorkflowError,
)


def comparison_cases() -> list[dict]:
    return build_cases(read_jsonl(Path("evals/commit12/cases.jsonl")))


def decision(proposal: ActionProposal, value: str) -> ApprovalDecision:
    return ApprovalDecision(
        action_id=proposal.action_id,
        decision=value,
        reviewer_id="commit13-test-reviewer",
        reason="Reviewed the exact proposal in the runtime comparison test.",
    )


class AlteredDiscountModel(FrozenCouponToolCallModel):
    def _tool_call(self) -> ResponseFunctionToolCall:
        tool_call = super()._tool_call()
        arguments = json.loads(tool_call.arguments)
        arguments["discount_percent"] = 50
        tool_call.arguments = json.dumps(arguments, sort_keys=True)
        return tool_call


class AgentsSDKWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cases = comparison_cases()

    def test_manifest_is_fixed_balanced_coupon_cohort(self):
        validate_cases(self.cases)

        self.assertEqual(len(self.cases), 20)
        self.assertEqual(
            {case["proposal"]["action"]["action_type"] for case in self.cases},
            {"ISSUE_COUPON"},
        )
        self.assertEqual(
            sum(case["inject_post_commit_failure"] for case in self.cases),
            5,
        )

    async def test_sdk_native_interruption_serializes_without_execution(self):
        proposal = ActionProposal.model_validate(self.cases[0]["proposal"])
        replay_model = FrozenCouponToolCallModel(proposal)
        with tempfile.TemporaryDirectory() as tmp:
            run = await AgentsSDKApprovalWorkflow(
                proposal,
                tmp,
                model=replay_model,
            ).start()

            self.assertEqual(run.status, "PENDING_APPROVAL")
            self.assertEqual(run.workflow_version, AGENTS_SDK_WORKFLOW_VERSION)
            self.assertTrue(Path(tmp, "run_state.json").exists())
            with ActionStore(Path(tmp, "actions.sqlite3")) as store:
                self.assertEqual(store.event_count(proposal.action_id), 0)
                self.assertEqual(
                    store.audit_events(proposal.action_id),
                    ["PROPOSED", "APPROVAL_REQUESTED"],
                )
            self.assertEqual(
                replay_model.settings_observed[0].reasoning.effort,
                "none",
            )

    async def test_fresh_sdk_instance_approves_and_executes_once(self):
        proposal = ActionProposal.model_validate(self.cases[0]["proposal"])
        with tempfile.TemporaryDirectory() as tmp:
            await AgentsSDKApprovalWorkflow(
                proposal,
                tmp,
                model=FrozenCouponToolCallModel(proposal),
            ).start()
            run = await AgentsSDKApprovalWorkflow(
                proposal,
                tmp,
                model=FrozenCouponToolCallModel(proposal),
            ).decide(decision(proposal, "APPROVED"))

            self.assertEqual(run.status, "EXECUTED")
            with ActionStore(Path(tmp, "actions.sqlite3")) as store:
                self.assertEqual(store.event_count(proposal.action_id), 1)
                self.assertEqual(
                    store.audit_events(proposal.action_id),
                    ["PROPOSED", "APPROVAL_REQUESTED", "APPROVED", "EXECUTED"],
                )

    async def test_rejection_finishes_without_tool_execution(self):
        proposal = ActionProposal.model_validate(self.cases[1]["proposal"])
        with tempfile.TemporaryDirectory() as tmp:
            await AgentsSDKApprovalWorkflow(
                proposal,
                tmp,
                model=FrozenCouponToolCallModel(proposal),
            ).start()
            run = await AgentsSDKApprovalWorkflow(
                proposal,
                tmp,
                model=FrozenCouponToolCallModel(proposal),
            ).decide(decision(proposal, "REJECTED"))

            self.assertEqual(run.status, "REJECTED")
            self.assertNotIn("tool_executed", run.transitions)
            with ActionStore(Path(tmp, "actions.sqlite3")) as store:
                self.assertEqual(store.event_count(proposal.action_id), 0)

    async def test_post_commit_failure_recovers_without_duplicate(self):
        proposal = ActionProposal.model_validate(self.cases[0]["proposal"])
        approval = decision(proposal, "APPROVED")
        with tempfile.TemporaryDirectory() as tmp:
            await AgentsSDKApprovalWorkflow(
                proposal,
                tmp,
                model=FrozenCouponToolCallModel(proposal),
            ).start()
            with self.assertRaisesRegex(Exception, "injected failure"):
                await AgentsSDKApprovalWorkflow(
                    proposal,
                    tmp,
                    model=FrozenCouponToolCallModel(proposal),
                    fail_after_event=True,
                ).decide(approval)

            run = await AgentsSDKApprovalWorkflow(
                proposal,
                tmp,
                model=FrozenCouponToolCallModel(proposal),
            ).recover()

            self.assertEqual(run.status, "EXECUTED")
            self.assertEqual(run.decision, approval)
            with ActionStore(Path(tmp, "actions.sqlite3")) as store:
                self.assertEqual(store.event_count(proposal.action_id), 1)
                self.assertEqual(
                    store.audit_events(proposal.action_id).count("EXECUTED"),
                    1,
                )

    async def test_model_cannot_change_tool_arguments_before_review(self):
        proposal = ActionProposal.model_validate(self.cases[0]["proposal"])
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(
                AgentsSDKWorkflowError,
                "differ from the immutable proposal",
            ):
                await AgentsSDKApprovalWorkflow(
                    proposal,
                    tmp,
                    model=AlteredDiscountModel(proposal),
                ).start()
            with ActionStore(Path(tmp, "actions.sqlite3")) as store:
                self.assertEqual(store.event_count(proposal.action_id), 0)

    def test_pinned_agents_sdk_and_stored_report_are_consistent(self):
        report = json.loads(
            Path("evals/commit13/reports/runtime_comparison.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(agents.__version__, "0.18.3")
        self.assertTrue(report["behavioral_parity"])
        self.assertEqual(report["failures"], [])
        for runtime in ("langgraph", "openai_agents_sdk"):
            metrics = report["runtimes"][runtime]
            self.assertEqual(metrics["approval_gated_rate_pct"], 100.0)
            self.assertEqual(metrics["state_recovery_rate_pct"], 100.0)
            self.assertEqual(metrics["duplicate_action_rate_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
