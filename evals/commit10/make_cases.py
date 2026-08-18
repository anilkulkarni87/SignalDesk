#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.tools import CDPTools
from src.tools.schemas import (
    CalculateCustomerMetricsInput,
    GetCampaignEligibilityInput,
    GetCustomerProfileInput,
)


RUBRIC_VERSION = "commit10_single_agent_tasks_v2"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def evidence(source_tool: str, field: str, value: Any) -> dict[str, Any]:
    return {"source_tool": source_tool, "field": field, "value": value}


def tool_rule(customer_id: str, **rules: Any) -> dict[str, Any]:
    return {"customer_id": customer_id, **rules}


def build_cases(source_cases: list[dict[str, Any]], tools: CDPTools) -> list[dict]:
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in source_cases:
        by_type[case["case_type"]].append(case)
    expected_types = {
        "multiple_warning_signals",
        "purchase_decline_only",
        "engagement_decline_only",
        "support_attention_only",
        "no_warning_signals",
    }
    if set(by_type) != expected_types or any(len(rows) != 10 for rows in by_type.values()):
        raise ValueError("Commit 10 requires the frozen 10-per-type Commit 05 cohort")

    cases = []

    for source in by_type["multiple_warning_signals"]:
        customer_id = source["customer_id"]
        metrics = tools.calculate_customer_metrics(
            CalculateCustomerMetricsInput(customer_id=customer_id)
        ).model_dump(mode="json")
        required = [
            evidence(
                "calculate_customer_metrics",
                f"{domain}.{field}",
                metrics[domain][field],
            )
            for domain in ("purchase", "engagement", "support")
            for field in source["required_evidence_all"]
            if field in metrics[domain]
        ]
        cases.append({
            "rubric_version": RUBRIC_VERSION,
            "case_id": f"agent_{source['case_id']}",
            "task_type": "multi_signal_investigation",
            "customer_id": customer_id,
            "question": (
                "Investigate the customer's combined warning signals. Validate the "
                "purchase pattern against the past year of order history and inspect "
                "the past 90 days of digital behavior. Explain contributing factors "
                "without claiming causality."
            ),
            "expected_tools": [
                "calculate_customer_metrics",
                "get_purchase_history",
                "get_customer_events",
            ],
            "allowed_tools": [
                "calculate_customer_metrics",
                "get_purchase_history",
                "get_customer_events",
            ],
            "argument_rules": {
                "calculate_customer_metrics": tool_rule(customer_id),
                "get_purchase_history": tool_rule(
                    customer_id,
                    days_equals=365,
                    limit_max=10,
                ),
                "get_customer_events": tool_rule(
                    customer_id,
                    days_equals=90,
                    limit_max=10,
                ),
            },
            "expected_conclusion_code": "MULTIPLE_WARNING_SIGNALS",
            "expected_risk_level": "HIGH",
            "required_evidence": required,
            "required_policy_families": [],
            "max_expected_tool_calls": 3,
        })

    for source in by_type["purchase_decline_only"]:
        customer_id = source["customer_id"]
        metrics = tools.calculate_customer_metrics(
            CalculateCustomerMetricsInput(customer_id=customer_id)
        ).model_dump(mode="json")
        cases.append({
            "rubric_version": RUBRIC_VERSION,
            "case_id": f"agent_{source['case_id']}",
            "task_type": "purchase_investigation",
            "customer_id": customer_id,
            "question": (
                "Explain why this customer's purchasing is flagged as declining. "
                "Compare the current purchase metrics with the past year of actual "
                "order history and identify the observable contributing factors."
            ),
            "expected_tools": [
                "calculate_customer_metrics",
                "get_purchase_history",
            ],
            "allowed_tools": [
                "calculate_customer_metrics",
                "get_purchase_history",
            ],
            "argument_rules": {
                "calculate_customer_metrics": tool_rule(customer_id),
                "get_purchase_history": tool_rule(
                    customer_id,
                    days_equals=365,
                    limit_max=10,
                ),
            },
            "expected_conclusion_code": "PURCHASE_DECLINE",
            "expected_risk_level": "MEDIUM",
            "required_evidence": [evidence(
                "calculate_customer_metrics",
                "purchase.purchase_decline_flag",
                metrics["purchase"]["purchase_decline_flag"],
            )],
            "required_policy_families": [],
            "max_expected_tool_calls": 2,
        })

    for source in by_type["engagement_decline_only"]:
        customer_id = source["customer_id"]
        metrics = tools.calculate_customer_metrics(
            CalculateCustomerMetricsInput(customer_id=customer_id)
        ).model_dump(mode="json")
        cases.append({
            "rubric_version": RUBRIC_VERSION,
            "case_id": f"agent_{source['case_id']}",
            "task_type": "behavior_investigation",
            "customer_id": customer_id,
            "question": (
                "Explain the customer's digital engagement decline. Compare the "
                "current engagement metrics with the past 90 days of behavioral "
                "events and summarize only observable factors."
            ),
            "expected_tools": [
                "calculate_customer_metrics",
                "get_customer_events",
            ],
            "allowed_tools": [
                "calculate_customer_metrics",
                "get_customer_events",
            ],
            "argument_rules": {
                "calculate_customer_metrics": tool_rule(customer_id),
                "get_customer_events": tool_rule(
                    customer_id,
                    days_equals=90,
                    limit_max=10,
                ),
            },
            "expected_conclusion_code": "ENGAGEMENT_DECLINE",
            "expected_risk_level": "MEDIUM",
            "required_evidence": [evidence(
                "calculate_customer_metrics",
                "engagement.engagement_decline_flag",
                metrics["engagement"]["engagement_decline_flag"],
            )],
            "required_policy_families": [],
            "max_expected_tool_calls": 2,
        })

    for source in by_type["support_attention_only"]:
        customer_id = source["customer_id"]
        metrics = tools.calculate_customer_metrics(
            CalculateCustomerMetricsInput(customer_id=customer_id)
        ).model_dump(mode="json")
        cases.append({
            "rubric_version": RUBRIC_VERSION,
            "case_id": f"agent_{source['case_id']}",
            "task_type": "support_policy_investigation",
            "customer_id": customer_id,
            "question": (
                "Explain the customer's support warning and identify the current "
                "approved support-policy guardrails an analyst should follow. Keep "
                "customer evidence separate from policy guidance."
            ),
            "expected_tools": [
                "calculate_customer_metrics",
                "search_knowledge_base",
            ],
            "allowed_tools": [
                "calculate_customer_metrics",
                "search_knowledge_base",
            ],
            "argument_rules": {
                "calculate_customer_metrics": tool_rule(customer_id),
                "search_knowledge_base": {
                    "required_families_across_calls": ["support"],
                    "top_k_min": 3,
                },
            },
            "expected_conclusion_code": "SUPPORT_ATTENTION",
            "expected_risk_level": "MEDIUM",
            "required_evidence": [evidence(
                "calculate_customer_metrics",
                "support.support_attention_flag",
                metrics["support"]["support_attention_flag"],
            )],
            "required_policy_families": ["support"],
            "max_expected_tool_calls": 2,
        })

    no_warning = by_type["no_warning_signals"]
    for source in no_warning[:5]:
        customer_id = source["customer_id"]
        profile = tools.get_customer_profile(
            GetCustomerProfileInput(customer_id=customer_id)
        ).model_dump(mode="json")
        cases.append({
            "rubric_version": RUBRIC_VERSION,
            "case_id": f"agent_profile_{source['case_id'][-2:]}",
            "task_type": "profile_lookup",
            "customer_id": customer_id,
            "question": (
                "Report the customer's current status, loyalty tier, country, and "
                "days since last seen. Do not perform a risk assessment."
            ),
            "expected_tools": ["get_customer_profile"],
            "allowed_tools": ["get_customer_profile"],
            "argument_rules": {
                "get_customer_profile": tool_rule(customer_id),
            },
            "expected_conclusion_code": "PROFILE_REPORTED",
            "expected_risk_level": "NOT_ASSESSED",
            "required_evidence": [
                evidence("get_customer_profile", field, profile[field])
                for field in (
                    "customer_status",
                    "loyalty_tier",
                    "country",
                    "days_since_last_seen",
                )
            ],
            "required_policy_families": [],
            "max_expected_tool_calls": 1,
        })

    for source in no_warning[5:]:
        customer_id = source["customer_id"]
        eligibility = tools.get_campaign_eligibility(
            GetCampaignEligibilityInput(customer_id=customer_id)
        ).model_dump(mode="json")
        conclusion = (
            "CAMPAIGN_BLOCKED"
            if eligibility["status"] == "BLOCKED"
            else "CAMPAIGN_REVIEW_REQUIRED"
        )
        cases.append({
            "rubric_version": RUBRIC_VERSION,
            "case_id": f"agent_campaign_{source['case_id'][-2:]}",
            "task_type": "campaign_readiness",
            "customer_id": customer_id,
            "question": (
                "Can this customer proceed to analyst review for retention outreach "
                "across available channels? Identify current consent and campaign-policy "
                "constraints. Do not claim final eligibility or execute anything."
            ),
            "expected_tools": [
                "get_campaign_eligibility",
                "search_knowledge_base",
            ],
            "allowed_tools": [
                "get_campaign_eligibility",
                "search_knowledge_base",
            ],
            "argument_rules": {
                "get_campaign_eligibility": tool_rule(
                    customer_id,
                    channel_must_be_null=True,
                ),
                "search_knowledge_base": {
                    "required_families_across_calls": ["campaigns", "consent"],
                    "families_per_call_max": 1,
                    "minimum_calls": 2,
                    "top_k_min": 3,
                },
            },
            "expected_conclusion_code": conclusion,
            "expected_risk_level": "NOT_ASSESSED",
            "required_evidence": [evidence(
                "get_campaign_eligibility",
                "status",
                eligibility["status"],
            )],
            "required_policy_families": ["campaigns", "consent"],
            "max_expected_tool_calls": 3,
        })

    if len(cases) != 50 or len({case["customer_id"] for case in cases}) != 50:
        raise ValueError("Commit 10 requires 50 tasks for 50 unique customers")
    return cases


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-cases",
        type=Path,
        default=Path("evals/commit05/cases.jsonl"),
    )
    parser.add_argument("--database", default="data/warehouse/signaldesk.duckdb")
    parser.add_argument("--corpus-dir", default="data/generated/knowledge")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/commit10/cases.jsonl"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with CDPTools(args.database, corpus_dir=args.corpus_dir) as tools:
        cases = build_cases(read_jsonl(args.source_cases), tools)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(case, sort_keys=True) + "\n" for case in cases),
        encoding="utf-8",
    )
    by_type: dict[str, int] = defaultdict(int)
    for case in cases:
        by_type[case["task_type"]] += 1
    print(json.dumps({
        "rubric_version": RUBRIC_VERSION,
        "cases": len(cases),
        "unique_customers": len({case["customer_id"] for case in cases}),
        "by_task_type": dict(sorted(by_type.items())),
        "output": str(args.output),
    }, indent=2))


if __name__ == "__main__":
    main()
