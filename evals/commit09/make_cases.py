#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path


CUSTOMER_IDS = [f"C{index:07d}" for index in range(1, 11)]

KNOWLEDGE_QUERIES = [
    ("email opt out suppression", ["consent"]),
    ("retention investigation no action", ["retention"]),
    ("retention offer cooling period", ["offers"]),
    ("open support case escalation handoff", ["support"]),
    ("refund return window", ["refunds"]),
    ("shipping delay threshold", ["shipping"]),
    ("loyalty tier benefits", ["loyalty"]),
    ("campaign contact frequency", ["campaigns"]),
    ("subscription cancellation handling", ["subscriptions"]),
    ("exact causal uplift retention discount", ["governance"]),
]


def valid_cases() -> list[dict]:
    cases = []
    for index, customer_id in enumerate(CUSTOMER_IDS, start=1):
        cases.extend([
            {
                "case_id": f"profile_valid_{index:02d}",
                "tool_name": "get_customer_profile",
                "arguments": {"customer_id": customer_id},
                "expected_success": True,
            },
            {
                "case_id": f"events_valid_{index:02d}",
                "tool_name": "get_customer_events",
                "arguments": {
                    "customer_id": customer_id,
                    "days": (7, 30, 90)[(index - 1) % 3],
                    "limit": 10,
                },
                "expected_success": True,
            },
            {
                "case_id": f"purchases_valid_{index:02d}",
                "tool_name": "get_purchase_history",
                "arguments": {
                    "customer_id": customer_id,
                    "days": 730,
                    "limit": 10,
                },
                "expected_success": True,
            },
            {
                "case_id": f"metrics_valid_{index:02d}",
                "tool_name": "calculate_customer_metrics",
                "arguments": {"customer_id": customer_id},
                "expected_success": True,
            },
            {
                "case_id": f"eligibility_valid_{index:02d}",
                "tool_name": "get_campaign_eligibility",
                "arguments": {
                    "customer_id": customer_id,
                    "channel": ("EMAIL", "SMS", "PUSH", None)[(index - 1) % 4],
                },
                "expected_success": True,
            },
            {
                "case_id": f"recommendation_valid_{index:02d}",
                "tool_name": "create_retention_recommendation",
                "arguments": {
                    "customer_id": customer_id,
                    "recommendation": "INVESTIGATE",
                    "rationale": (
                        "Review customer evidence and current policy before deciding "
                        "whether any retention intervention is appropriate."
                    ),
                    "evidence_features": [
                        "purchase_decline_flag",
                        "engagement_decline_flag",
                    ],
                    "policy_document_ids": ["KB-00779"],
                },
                "expected_success": True,
            },
        ])

    for index, (query, families) in enumerate(KNOWLEDGE_QUERIES, start=1):
        cases.append({
            "case_id": f"knowledge_valid_{index:02d}",
            "tool_name": "search_knowledge_base",
            "arguments": {"query": query, "families": families, "top_k": 5},
            "expected_success": True,
        })
    return cases


def invalid_cases() -> list[dict]:
    definitions = {
        "get_customer_profile": [
            ({"customer_id": "bad"}, "VALIDATION_ERROR"),
            ({"customer_id": "C9999999"}, "NOT_FOUND"),
            ({"customer_id": ""}, "VALIDATION_ERROR"),
            ({"customer_id": "C0000001", "include_email": True}, "VALIDATION_ERROR"),
            ({"customer_id": "C1' OR '1'='1"}, "VALIDATION_ERROR"),
        ],
        "get_customer_events": [
            ({"customer_id": "C0000001", "days": 0}, "VALIDATION_ERROR"),
            ({"customer_id": "C0000001", "days": 91}, "VALIDATION_ERROR"),
            ({"customer_id": "C0000001", "limit": 0}, "VALIDATION_ERROR"),
            ({"customer_id": "C0000001", "event_types": ["login"]}, "VALIDATION_ERROR"),
            ({"customer_id": "C9999999"}, "NOT_FOUND"),
        ],
        "get_purchase_history": [
            ({"customer_id": "C0000001", "days": 0}, "VALIDATION_ERROR"),
            ({"customer_id": "C0000001", "days": 731}, "VALIDATION_ERROR"),
            ({"customer_id": "C0000001", "limit": 51}, "VALIDATION_ERROR"),
            ({"customer_id": "C9999999"}, "NOT_FOUND"),
            ({"customer_id": "C0000001", "currency": "USD"}, "VALIDATION_ERROR"),
        ],
        "search_knowledge_base": [
            ({"query": ""}, "VALIDATION_ERROR"),
            ({"query": "ab"}, "VALIDATION_ERROR"),
            ({"query": "retention", "top_k": 0}, "VALIDATION_ERROR"),
            ({"query": "retention", "top_k": 11}, "VALIDATION_ERROR"),
            ({"query": "retention", "families": ["legal"]}, "VALIDATION_ERROR"),
        ],
        "calculate_customer_metrics": [
            ({"customer_id": "bad"}, "VALIDATION_ERROR"),
            ({"customer_id": "C9999999"}, "NOT_FOUND"),
            ({"customer_id": ""}, "VALIDATION_ERROR"),
            ({"customer_id": "C0000001", "metric": "secret"}, "VALIDATION_ERROR"),
            ({}, "VALIDATION_ERROR"),
        ],
        "get_campaign_eligibility": [
            ({"customer_id": "bad"}, "VALIDATION_ERROR"),
            ({"customer_id": "C9999999"}, "NOT_FOUND"),
            ({"customer_id": "C0000001", "channel": "PHONE"}, "VALIDATION_ERROR"),
            ({"customer_id": "C0000001", "execute": True}, "VALIDATION_ERROR"),
            ({}, "VALIDATION_ERROR"),
        ],
        "create_retention_recommendation": [
            ({
                "customer_id": "C0000001",
                "recommendation": "INVESTIGATE",
                "rationale": "Review evidence before making a decision.",
                "evidence_features": ["purchase_decline_flag"],
                "policy_document_ids": ["KB-99999"],
            }, "NOT_FOUND"),
            ({
                "customer_id": "C0000001",
                "recommendation": "INVESTIGATE",
                "rationale": "Review evidence before making a decision.",
                "evidence_features": ["purchase_decline_flag", "purchase_decline_flag"],
                "policy_document_ids": ["KB-00779"],
            }, "VALIDATION_ERROR"),
            ({
                "customer_id": "C0000001",
                "recommendation": "INVESTIGATE",
                "rationale": "short",
                "evidence_features": ["purchase_decline_flag"],
                "policy_document_ids": ["KB-00779"],
            }, "VALIDATION_ERROR"),
            ({
                "customer_id": "C0000001",
                "recommendation": "SEND_EMAIL",
                "rationale": "Attempt an unsupported automatic customer action.",
                "evidence_features": ["purchase_decline_flag"],
                "policy_document_ids": ["KB-00779"],
            }, "VALIDATION_ERROR"),
            ({
                "customer_id": "C0000006",
                "recommendation": "RETENTION_OFFER",
                "rationale": "Attempt a draft when every communication channel is blocked.",
                "evidence_features": ["customer_status"],
                "policy_document_ids": ["KB-00779"],
            }, "CONFLICT"),
        ],
    }

    cases = []
    for tool_name, entries in definitions.items():
        for index, (arguments, expected_error) in enumerate(entries, start=1):
            cases.append({
                "case_id": f"{tool_name}_invalid_{index:02d}",
                "tool_name": tool_name,
                "arguments": arguments,
                "expected_success": False,
                "expected_error_code": expected_error,
            })
    return cases


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/commit09/cases.jsonl"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases = valid_cases() + invalid_cases()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(case, sort_keys=True) + "\n" for case in cases),
        encoding="utf-8",
    )
    print(json.dumps({
        "cases": len(cases),
        "valid_cases": sum(case["expected_success"] for case in cases),
        "invalid_cases": sum(not case["expected_success"] for case in cases),
        "tools": sorted({case["tool_name"] for case in cases}),
        "output": str(args.output),
    }, indent=2))


if __name__ == "__main__":
    main()
