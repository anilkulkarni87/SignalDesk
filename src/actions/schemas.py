from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from src.agent.schemas import StrictModel


ActionType = Literal[
    "ISSUE_COUPON",
    "ENROLL_CAMPAIGN",
    "CREATE_SUPPORT_CASE",
    "FLAG_ACCOUNT",
    "SEND_RETENTION_OFFER",
]
Decision = Literal["APPROVED", "REJECTED"]


class CouponAction(StrictModel):
    action_type: Literal["ISSUE_COUPON"] = "ISSUE_COUPON"
    coupon_code: str = Field(pattern=r"^[A-Z0-9_-]{3,32}$")
    discount_percent: int = Field(ge=1, le=50)
    expires_in_days: int = Field(ge=1, le=90)


class CampaignEnrollmentAction(StrictModel):
    action_type: Literal["ENROLL_CAMPAIGN"] = "ENROLL_CAMPAIGN"
    campaign_id: str = Field(pattern=r"^CMP-[A-Z0-9_-]{3,32}$")
    channel: Literal["EMAIL", "SMS", "PUSH"]


class SupportCaseAction(StrictModel):
    action_type: Literal["CREATE_SUPPORT_CASE"] = "CREATE_SUPPORT_CASE"
    priority: Literal["LOW", "MEDIUM", "HIGH", "URGENT"]
    summary: str = Field(min_length=10, max_length=500)


class AccountFlagAction(StrictModel):
    action_type: Literal["FLAG_ACCOUNT"] = "FLAG_ACCOUNT"
    flag_code: Literal[
        "PURCHASE_REVIEW",
        "SUPPORT_ATTENTION",
        "CONSENT_REVIEW",
        "RETENTION_RISK",
    ]
    reason: str = Field(min_length=10, max_length=500)


class RetentionOfferAction(StrictModel):
    action_type: Literal["SEND_RETENTION_OFFER"] = "SEND_RETENTION_OFFER"
    offer_id: str = Field(pattern=r"^OFFER-[A-Z0-9_-]{3,32}$")
    channel: Literal["EMAIL", "SMS", "PUSH"]


ActionPayload = Annotated[
    CouponAction
    | CampaignEnrollmentAction
    | SupportCaseAction
    | AccountFlagAction
    | RetentionOfferAction,
    Field(discriminator="action_type"),
]


class ActionProposal(StrictModel):
    action_id: str = Field(pattern=r"^ACT-[a-f0-9]{24}$")
    customer_id: str = Field(pattern=r"^C\d{7}$")
    action: ActionPayload
    recommendation: str = Field(min_length=10, max_length=500)
    reason: str = Field(min_length=10, max_length=1000)
    expected_impact: str = Field(min_length=10, max_length=500)
    source_case_id: str = Field(min_length=3, max_length=200)
    proposed_by: Literal["signaldesk_agent", "signaldesk_workspace"] = (
        "signaldesk_agent"
    )

    @classmethod
    def build(
        cls,
        *,
        customer_id: str,
        action: ActionPayload,
        recommendation: str,
        reason: str,
        expected_impact: str,
        source_case_id: str,
        proposed_by: Literal["signaldesk_agent", "signaldesk_workspace"] = (
            "signaldesk_agent"
        ),
    ) -> "ActionProposal":
        identity = {
            "customer_id": customer_id,
            "action": action.model_dump(mode="json"),
            "recommendation": recommendation,
            "reason": reason,
            "expected_impact": expected_impact,
            "source_case_id": source_case_id,
            "proposed_by": proposed_by,
        }
        digest = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:24]
        return cls(action_id=f"ACT-{digest}", **identity)

    @model_validator(mode="after")
    def action_id_matches_payload(self) -> "ActionProposal":
        identity = self.model_dump(mode="json", exclude={"action_id"})
        digest = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:24]
        if self.action_id != f"ACT-{digest}":
            raise ValueError("action_id does not match the exact proposal payload")
        return self


class ApprovalDecision(StrictModel):
    action_id: str = Field(pattern=r"^ACT-[a-f0-9]{24}$")
    decision: Decision
    reviewer_id: str = Field(min_length=3, max_length=100)
    reason: str = Field(min_length=3, max_length=500)


class ApprovalRequest(StrictModel):
    action_id: str
    customer_id: str
    action: ActionPayload
    recommendation: str
    reason: str
    expected_impact: str
    allowed_decisions: list[Decision] = Field(
        default_factory=lambda: ["APPROVED", "REJECTED"]
    )

    @field_validator("allowed_decisions")
    @classmethod
    def decisions_are_fixed(cls, value: list[str]) -> list[str]:
        if value != ["APPROVED", "REJECTED"]:
            raise ValueError("allowed decisions cannot be changed")
        return value


class ActionRun(StrictModel):
    workflow_version: str
    thread_id: str
    action_id: str
    status: Literal["PENDING_APPROVAL", "REJECTED", "EXECUTED"]
    approval_request: ApprovalRequest | None = None
    decision: ApprovalDecision | None = None
    synthetic_event_id: str | None = None
    transitions: list[str]

    @model_validator(mode="after")
    def status_fields_are_consistent(self) -> "ActionRun":
        if self.status == "PENDING_APPROVAL":
            if self.approval_request is None or self.decision is not None:
                raise ValueError("pending runs require a request and no decision")
        elif self.decision is None:
            raise ValueError("completed runs require a decision")
        if self.status == "EXECUTED" and self.synthetic_event_id is None:
            raise ValueError("executed runs require a synthetic event")
        if self.status != "EXECUTED" and self.synthetic_event_id is not None:
            raise ValueError("only executed runs may contain a synthetic event")
        return self
