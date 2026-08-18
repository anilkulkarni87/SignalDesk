from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from evals.commit12.make_cases import build_cases, read_jsonl, validate_cases
from src.actions import (
    ActionProposal,
    ActionStoreConflict,
    ApprovalDecision,
    CouponAction,
    HumanApprovalWorkflow,
)
from src.actions.workflow import ApprovalWorkflowError, WORKFLOW_VERSION


def proposal(source_case_id: str = "unit-case") -> ActionProposal:
    return ActionProposal.build(
        customer_id="C0000001",
        action=CouponAction(
            coupon_code="SAVE10",
            discount_percent=10,
            expires_in_days=30,
        ),
        recommendation="Issue a bounded coupon after human review.",
        reason="The customer qualifies for this synthetic retention experiment.",
        expected_impact="The coupon may improve retention without automatic execution.",
        source_case_id=source_case_id,
    )


def decision(item: ActionProposal, value: str) -> ApprovalDecision:
    return ApprovalDecision(
        action_id=item.action_id,
        decision=value,
        reviewer_id="reviewer-1",
        reason="Reviewed the exact proposed action and supporting evidence.",
    )


class HumanApprovalWorkflowTests(unittest.TestCase):
    def test_action_id_is_deterministic_and_bound_to_exact_payload(self):
        first = proposal()
        second = proposal()

        self.assertEqual(first.action_id, second.action_id)
        tampered = first.model_dump(mode="json")
        tampered["action"]["discount_percent"] = 20
        with self.assertRaisesRegex(ValidationError, "action_id does not match"):
            ActionProposal.model_validate(tampered)

    def test_start_pauses_before_any_synthetic_event(self):
        item = proposal()
        with tempfile.TemporaryDirectory() as tmp:
            with HumanApprovalWorkflow(tmp) as workflow:
                run = workflow.start(item)

                self.assertEqual(run.status, "PENDING_APPROVAL")
                self.assertEqual(run.workflow_version, WORKFLOW_VERSION)
                self.assertEqual(workflow.store.event_count(), 0)
                self.assertEqual(
                    workflow.store.audit_events(item.action_id),
                    ["PROPOSED", "APPROVAL_REQUESTED"],
                )
                self.assertEqual(run.approval_request.action, item.action)
                with self.assertRaisesRegex(
                    ActionStoreConflict,
                    "has not been approved",
                ):
                    workflow.store.execute_approved(item)

    def test_approval_survives_restart_and_executes_once(self):
        item = proposal()
        with tempfile.TemporaryDirectory() as tmp:
            with HumanApprovalWorkflow(tmp) as workflow:
                workflow.start(item)
            with HumanApprovalWorkflow(tmp) as workflow:
                run = workflow.decide(
                    item.action_id,
                    decision(item, "APPROVED"),
                )

                self.assertEqual(run.status, "EXECUTED")
                self.assertEqual(workflow.store.event_count(item.action_id), 1)
                self.assertEqual(
                    workflow.store.audit_events(item.action_id),
                    ["PROPOSED", "APPROVAL_REQUESTED", "APPROVED", "EXECUTED"],
                )

    def test_rejection_is_audited_and_never_executes(self):
        item = proposal()
        with tempfile.TemporaryDirectory() as tmp:
            with HumanApprovalWorkflow(tmp) as workflow:
                workflow.start(item)
                run = workflow.decide(
                    item.action_id,
                    decision(item, "REJECTED"),
                )

                self.assertEqual(run.status, "REJECTED")
                self.assertEqual(workflow.store.event_count(item.action_id), 0)
                self.assertEqual(
                    workflow.store.audit_events(item.action_id),
                    ["PROPOSED", "APPROVAL_REQUESTED", "REJECTED"],
                )

    def test_decision_for_another_action_is_rejected(self):
        first = proposal("first-case")
        second = proposal("second-case")
        with tempfile.TemporaryDirectory() as tmp:
            with HumanApprovalWorkflow(tmp) as workflow:
                workflow.start(first)

                with self.assertRaisesRegex(
                    ApprovalWorkflowError,
                    "does not match thread",
                ):
                    workflow.decide(
                        first.action_id,
                        decision(second, "APPROVED"),
                    )
                self.assertEqual(workflow.store.event_count(), 0)

    def test_post_commit_failure_recovers_without_duplicate_event(self):
        item = proposal()
        with tempfile.TemporaryDirectory() as tmp:
            with HumanApprovalWorkflow(
                tmp,
                fail_after_event_action_ids={item.action_id},
            ) as workflow:
                workflow.start(item)
                with self.assertRaisesRegex(RuntimeError, "injected failure"):
                    workflow.decide(
                        item.action_id,
                        decision(item, "APPROVED"),
                    )
                self.assertEqual(workflow.store.event_count(item.action_id), 1)

            with HumanApprovalWorkflow(tmp) as workflow:
                with self.assertRaisesRegex(
                    ApprovalWorkflowError,
                    "call recover",
                ):
                    workflow.start(item)
                run = workflow.recover(item.action_id)

                self.assertEqual(run.status, "EXECUTED")
                self.assertEqual(workflow.store.event_count(item.action_id), 1)
                self.assertEqual(
                    workflow.store.audit_events(item.action_id).count("EXECUTED"),
                    1,
                )

    def test_completed_thread_cannot_receive_a_second_decision(self):
        item = proposal()
        with tempfile.TemporaryDirectory() as tmp:
            with HumanApprovalWorkflow(tmp) as workflow:
                workflow.start(item)
                workflow.decide(item.action_id, decision(item, "APPROVED"))

                with self.assertRaisesRegex(
                    ApprovalWorkflowError,
                    "not waiting for approval",
                ):
                    workflow.decide(item.action_id, decision(item, "APPROVED"))
                self.assertEqual(workflow.store.event_count(item.action_id), 1)

    def test_manifest_pairs_every_frozen_customer_with_both_decisions(self):
        cases = build_cases(read_jsonl(Path("evals/commit10/cases.jsonl")))

        validate_cases(cases)
        self.assertEqual(len(cases), 100)
        self.assertEqual(
            sum(case["decision"] == "APPROVED" for case in cases),
            50,
        )
        self.assertEqual(
            {
                action_type: sum(
                    case["proposal"]["action"]["action_type"] == action_type
                    for case in cases
                )
                for action_type in {
                    case["proposal"]["action"]["action_type"]
                    for case in cases
                }
            },
            {
                "ISSUE_COUPON": 20,
                "ENROLL_CAMPAIGN": 20,
                "CREATE_SUPPORT_CASE": 20,
                "FLAG_ACCOUNT": 20,
                "SEND_RETENTION_OFFER": 20,
            },
        )


if __name__ == "__main__":
    unittest.main()
