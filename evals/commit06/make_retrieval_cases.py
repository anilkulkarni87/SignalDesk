#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from src.retrieval.documents import KnowledgeDocument, load_documents


@dataclass(frozen=True)
class CaseDefinition:
    case_id: str
    category: str
    query: str
    selectors: tuple[tuple[str, str], ...]


TOPIC_QUERIES = {
    "retention": {
        "when no action is appropriate":
            "When should the team leave an at-risk customer alone instead of intervening?",
        "when a retention offer may be considered":
            "What evidence should be reviewed before considering a customer save incentive?",
        "when support escalation should take priority":
            "Should an unresolved service issue be handled before a retention incentive?",
        "how to review declining purchase behavior":
            "How should falling order frequency and reduced spending be investigated?",
        "how to interpret weakening engagement":
            "How should weakening email and website activity be interpreted?",
    },
    "offers": {
        "minimum eligibility requirements":
            "What basic requirements must be met before a retention offer is allowed?",
        "recent-offer cooling periods":
            "How long should we wait after a customer already received an incentive?",
        "discount exclusions":
            "Which conditions exclude a customer from receiving a promotional discount?",
        "maximum promotion frequency":
            "How frequently may promotional offers be sent to the same customer?",
        "margin protection rules":
            "How do margin safeguards constrain customer incentive approval?",
    },
    "support": {
        "shipping-related escalation":
            "When should a delivery problem be escalated to customer support?",
        "damaged-item escalation":
            "What is the escalation process when a customer reports damaged merchandise?",
        "unresolved refund cases":
            "How should support handle a refund case that remains unresolved?",
        "high-priority service recovery":
            "Which service failures require high-priority recovery review?",
        "required handoff context":
            "What details must accompany a retention-to-support handoff?",
    },
    "shipping": {
        "delay thresholds":
            "How late must an order be before it requires a delivery service review?",
        "carrier exception handling":
            "What should the team do when a carrier reports a delivery exception?",
        "replacement eligibility":
            "When is a replacement shipment allowed for a delivery problem?",
        "customer communication":
            "How should customers be contacted about delayed shipments?",
        "service recovery after repeated delays":
            "What recovery steps apply after a customer experiences repeated late deliveries?",
    },
    "refunds": {
        "refund eligibility":
            "What conditions make a purchase eligible for a refund?",
        "return windows":
            "How long after delivery may a customer return an item?",
        "damaged-item refunds":
            "What refund process applies when the delivered item is damaged?",
        "refund approval exceptions":
            "Who must approve a refund that falls outside standard rules?",
        "non-refundable conditions":
            "Which purchases or conditions are excluded from refunds?",
    },
    "loyalty": {
        "tier benefits":
            "Which benefits are available to each loyalty program tier?",
        "tier retention":
            "What must a member do to keep their current loyalty tier?",
        "credit eligibility":
            "When is a customer eligible for loyalty credit?",
        "benefit expiration":
            "When do unused loyalty benefits expire?",
        "loyalty exceptions":
            "How should exceptions to standard loyalty rules be reviewed?",
    },
    "campaigns": {
        "contact frequency":
            "How often may lifecycle marketing contact the same customer?",
        "win-back eligibility":
            "What makes a customer eligible for a win-back campaign?",
        "campaign suppression":
            "When must a customer be suppressed from an outbound campaign?",
        "channel selection":
            "How should marketing choose the permitted channel for a campaign?",
        "recent campaign exposure":
            "How does a recent marketing message affect the next campaign decision?",
    },
    "subscriptions": {
        "cancellation handling":
            "What steps should follow a customer subscription cancellation?",
        "pause eligibility":
            "When may a customer pause a subscription instead of cancelling it?",
        "renewal issues":
            "How should the team investigate a problem during subscription renewal?",
        "failed renewal follow-up":
            "What follow-up is required after a subscription payment fails to renew?",
        "replenishment exceptions":
            "How should an exception to the replenishment schedule be handled?",
    },
    "consent": {
        "email opt-out":
            "May we send marketing email after the customer has opted out?",
        "sms opt-out":
            "What restriction applies after a customer withdraws text-message consent?",
        "push notification consent":
            "What permission is required before sending a promotional push notification?",
        "effective consent timestamps":
            "Which consent timestamp controls whether a planned message is permitted?",
        "suppression requirements":
            "When must communication channels be suppressed because consent is absent?",
    },
}

GAP_QUERIES = {
    "exact causal uplift from retention discounts":
        "How much incremental retention will a discount cause for this customer?",
    "customer-specific discretionary discount amount":
        "What exact personalized discount percentage should this customer receive?",
    "automatic execution of retention interventions":
        "Can SignalDesk automatically send the recommended retention intervention?",
    "support compensation beyond documented service recovery limits":
        "May support grant compensation above the documented recovery limit?",
}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-dir", default="data/generated/knowledge")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/commit06/retrieval_cases.jsonl"),
    )
    return parser.parse_args()


def case_definitions() -> list[CaseDefinition]:
    definitions = []
    for family, topics in TOPIC_QUERIES.items():
        for index, (topic, query) in enumerate(topics.items(), start=1):
            definitions.append(CaseDefinition(
                case_id=f"{family}_{index:02d}",
                category=family,
                query=query,
                selectors=((family, topic),),
            ))

    for index, (topic, query) in enumerate(GAP_QUERIES.items(), start=1):
        definitions.append(CaseDefinition(
            case_id=f"known_gap_{index:02d}",
            category="governance",
            query=query,
            selectors=(("governance", topic),),
        ))

    definitions.append(CaseDefinition(
        case_id="cross_family_01",
        category="cross_family",
        query=(
            "Before sending a win-back message, which rules require campaign "
            "suppression when the customer has opted out?"
        ),
        selectors=(
            ("campaigns", "campaign suppression"),
            ("consent", "suppression requirements"),
        ),
    ))
    return definitions


def matches(document: KnowledgeDocument, selectors: tuple[tuple[str, str], ...]) -> bool:
    topic = str(document.metadata.get("topic", ""))
    return any(
        document.family == family and topic == expected_topic
        for family, expected_topic in selectors
    )


def build_cases(documents: list[KnowledgeDocument]) -> list[dict]:
    authoritative = [
        document
        for document in documents
        if document.status == "CURRENT" and document.authority == "APPROVED"
    ]
    cases = []
    for definition in case_definitions():
        relevant = sorted(
            document.document_id
            for document in authoritative
            if matches(document, definition.selectors)
        )
        if not relevant:
            raise ValueError(
                f"{definition.case_id} has no current approved relevant documents"
            )
        cases.append({
            "case_id": definition.case_id,
            "category": definition.category,
            "query": definition.query,
            "relevant_document_ids": relevant,
            "relevance_selectors": [
                {"family": family, "topic": topic}
                for family, topic in definition.selectors
            ],
            "statuses": ["CURRENT"],
            "authorities": ["APPROVED"],
        })

    if len(cases) != 50:
        raise ValueError(f"Expected 50 retrieval cases, built {len(cases)}")
    return cases


def main():
    args = parse_args()
    cases = build_cases(load_documents(args.corpus_dir))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(case, sort_keys=True) + "\n" for case in cases),
        encoding="utf-8",
    )
    print(json.dumps({
        "cases": len(cases),
        "output": str(args.output),
        "categories": sorted({case["category"] for case in cases}),
    }, indent=2))


if __name__ == "__main__":
    main()
