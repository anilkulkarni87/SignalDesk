#!/usr/bin/env python3
"""
Generate a synthetic NovaCart business-knowledge corpus for later RAG experiments.

The corpus intentionally contains:
- authoritative current policies
- superseded/older versions
- playbooks and procedures
- FAQs and operational guidance
- overlapping terminology
- cross-references
- partial/incomplete documents
- deliberate knowledge gaps

The goal is not "1,000 perfect documents". The goal is a controlled corpus
that can expose realistic retrieval, freshness, conflict, and abstention problems.

Example:
    python data/knowledge/generate_knowledge_docs.py \
        --documents 1000 \
        --output-dir data/generated/knowledge \
        --seed 42
"""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
from collections import Counter
from datetime import date, timedelta
from pathlib import Path


BASE_DATE = date(2026, 8, 1)

FAMILIES = {
    "retention": {
        "weight": 0.18,
        "titles": [
            "Retention Intervention Playbook",
            "At-Risk Customer Review Guide",
            "Customer Save Decision Framework",
            "Retention Specialist Operating Guide",
        ],
        "topics": [
            "when no action is appropriate",
            "when a retention offer may be considered",
            "when support escalation should take priority",
            "how to review declining purchase behavior",
            "how to interpret weakening engagement",
        ],
    },
    "offers": {
        "weight": 0.14,
        "titles": [
            "Retention Offer Eligibility Policy",
            "Promotional Offer Guardrails",
            "Discount Approval Rules",
            "Customer Incentive Policy",
        ],
        "topics": [
            "minimum eligibility requirements",
            "recent-offer cooling periods",
            "discount exclusions",
            "maximum promotion frequency",
            "margin protection rules",
        ],
    },
    "support": {
        "weight": 0.15,
        "titles": [
            "Customer Support Escalation Playbook",
            "Retention-to-Support Handoff Procedure",
            "Service Recovery Guidelines",
            "Customer Issue Triage Guide",
        ],
        "topics": [
            "shipping-related escalation",
            "damaged-item escalation",
            "unresolved refund cases",
            "high-priority service recovery",
            "required handoff context",
        ],
    },
    "shipping": {
        "weight": 0.11,
        "titles": [
            "Shipping Delay Policy",
            "Lost Shipment Procedure",
            "Delivery Exception Guide",
            "Late Delivery Service Policy",
        ],
        "topics": [
            "delay thresholds",
            "carrier exception handling",
            "replacement eligibility",
            "customer communication",
            "service recovery after repeated delays",
        ],
    },
    "refunds": {
        "weight": 0.11,
        "titles": [
            "Refund and Return Policy",
            "Refund Escalation Procedure",
            "Return Eligibility Guide",
            "Refund Exception Rules",
        ],
        "topics": [
            "refund eligibility",
            "return windows",
            "damaged-item refunds",
            "refund approval exceptions",
            "non-refundable conditions",
        ],
    },
    "loyalty": {
        "weight": 0.09,
        "titles": [
            "Loyalty Program Policy",
            "Loyalty Tier Benefits Guide",
            "Loyalty Retention Procedure",
            "Loyalty Credit Rules",
        ],
        "topics": [
            "tier benefits",
            "tier retention",
            "credit eligibility",
            "benefit expiration",
            "loyalty exceptions",
        ],
    },
    "campaigns": {
        "weight": 0.10,
        "titles": [
            "Campaign Contact Policy",
            "Win-Back Campaign Guide",
            "Campaign Frequency Rules",
            "Customer Messaging Standards",
        ],
        "topics": [
            "contact frequency",
            "win-back eligibility",
            "campaign suppression",
            "channel selection",
            "recent campaign exposure",
        ],
    },
    "subscriptions": {
        "weight": 0.07,
        "titles": [
            "Subscription Service Policy",
            "Subscription Cancellation Guide",
            "Replenishment Program Procedure",
            "Subscription Recovery Playbook",
        ],
        "topics": [
            "cancellation handling",
            "pause eligibility",
            "renewal issues",
            "failed renewal follow-up",
            "replenishment exceptions",
        ],
    },
    "consent": {
        "weight": 0.05,
        "titles": [
            "Customer Communication Consent Policy",
            "Marketing Consent Operating Standard",
            "Channel Opt-Out Procedure",
            "Consent Enforcement Guide",
        ],
        "topics": [
            "email opt-out",
            "sms opt-out",
            "push notification consent",
            "effective consent timestamps",
            "suppression requirements",
        ],
    },
}

DOC_TYPES = [
    ("POLICY", 0.34),
    ("PLAYBOOK", 0.24),
    ("PROCEDURE", 0.22),
    ("FAQ", 0.10),
    ("OPERATING_GUIDE", 0.10),
]

STATUSES = [
    ("CURRENT", 0.70),
    ("SUPERSEDED", 0.16),
    ("DRAFT", 0.08),
    ("INCOMPLETE", 0.06),
]

AUTHOR_TEAMS = [
    "Retention Operations",
    "Customer Support",
    "Lifecycle Marketing",
    "Legal Operations",
    "Commerce Operations",
    "Customer Experience",
]

AMBIGUOUS_TERMS = {
    "save offer": ["retention offer", "customer save incentive", "win-back incentive"],
    "support escalation": ["service escalation", "customer-care handoff", "specialist escalation"],
    "cooling period": ["offer cooldown", "contact cooling window", "suppression interval"],
    "at-risk customer": ["retention candidate", "risk-listed customer", "declining customer"],
}

KNOWN_GAPS = [
    {
        "gap_id": "GAP-001",
        "topic": "exact causal uplift from retention discounts",
        "reason": "NovaCart has no authoritative policy or experiment result establishing who is incrementally saved by a discount.",
        "expected_behavior": "Do not infer causal benefit from churn risk or historical offer use.",
    },
    {
        "gap_id": "GAP-002",
        "topic": "customer-specific discretionary discount amount",
        "reason": "No approved rule maps an individual customer profile to an optimized discount percentage.",
        "expected_behavior": "Do not invent personalized discount values.",
    },
    {
        "gap_id": "GAP-003",
        "topic": "automatic execution of retention interventions",
        "reason": "V1 requires human approval and has no authoritative automation policy.",
        "expected_behavior": "Recommend only; do not claim an action can be executed automatically.",
    },
    {
        "gap_id": "GAP-004",
        "topic": "support compensation beyond documented service recovery limits",
        "reason": "No durable source authorizes exceptions above the documented limits.",
        "expected_behavior": "Escalate or state insufficient evidence.",
    },
]


def parse_args():
    p = argparse.ArgumentParser(description="Generate NovaCart synthetic knowledge documents.")
    p.add_argument("--documents", type=int, default=1000)
    p.add_argument("--output-dir", type=Path, default=Path("data/generated/knowledge"))
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args()


def weighted_choice(rng, pairs):
    x = rng.random()
    total = 0.0
    for value, weight in pairs:
        total += weight
        if x <= total:
            return value
    return pairs[-1][0]


def choose_family(rng):
    pairs = [(name, cfg["weight"]) for name, cfg in FAMILIES.items()]
    return weighted_choice(rng, pairs)


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value


def effective_dates(rng, status):
    effective = BASE_DATE - timedelta(days=rng.randint(30, 900))
    reviewed = effective + timedelta(days=rng.randint(10, 180))
    superseded_by = ""
    if status == "SUPERSEDED":
        reviewed = effective + timedelta(days=rng.randint(30, 400))
    return effective.isoformat(), reviewed.isoformat(), superseded_by


def terminology_variant(rng, text):
    for canonical, variants in AMBIGUOUS_TERMS.items():
        if canonical in text and rng.random() < 0.55:
            text = text.replace(canonical, rng.choice(variants))
    return text


def policy_content(rng, family, doc_type, status, topic, version):
    cfg = FAMILIES[family]

    if family == "consent":
        rule = (
            "If a customer has an effective channel opt-out before the proposed contact time, "
            "the customer must not be contacted on that channel. This is a hard operational constraint."
        )
    elif family == "offers":
        cooldown = rng.choice([14, 21, 30, 45])
        rule = (
            f"A customer should not receive another retention offer within {cooldown} days of a prior "
            "retention incentive unless an approved exception is documented. Offer eligibility does not "
            "prove that an offer will improve retention."
        )
    elif family == "support":
        rule = (
            "A customer with an unresolved service problem should be evaluated for support escalation "
            "before a retention incentive is considered. The handoff must include the customer identifier, "
            "issue summary, relevant order or ticket references, and supporting evidence."
        )
    elif family == "shipping":
        threshold = rng.choice([3, 5, 7])
        rule = (
            f"Orders delayed at least {threshold} days beyond the expected delivery date require a service review. "
            "Repeated delays may justify escalation, but compensation must remain within documented service-recovery limits."
        )
    elif family == "refunds":
        window = rng.choice([30, 45, 60])
        rule = (
            f"Standard returns are generally eligible within {window} days of delivery when product-condition "
            "requirements are met. Refund exceptions require documented approval."
        )
    elif family == "loyalty":
        rule = (
            "Loyalty status may inform customer context, but tier membership alone does not authorize a retention offer. "
            "Existing benefit rules and expiration dates must be checked separately."
        )
    elif family == "campaigns":
        days = rng.choice([7, 14, 21])
        rule = (
            f"Recent campaign exposure within {days} days should be reviewed before recommending another outbound "
            "retention contact. Existing channel consent and suppression rules remain controlling."
        )
    elif family == "subscriptions":
        rule = (
            "Subscription cancellation or failed renewal may be a useful customer signal, but it must be interpreted "
            "with purchase, engagement, and support context before an intervention is recommended."
        )
    else:
        rule = (
            "Retention investigation should first establish what materially changed in customer behavior. "
            "The specialist should distinguish evidence of disengagement from evidence of an unresolved service issue "
            "before choosing NO_ACTION, RETENTION_OFFER, or ESCALATE_TO_SUPPORT."
        )

    exception = rng.choice([
        "When evidence is incomplete, the reviewer should record the missing evidence and avoid unsupported conclusions.",
        "Conflicting evidence must be surfaced rather than silently resolved.",
        "A recommendation must cite the material evidence used to support it.",
        "Human review remains required before any consequential intervention.",
    ])

    source_note = rng.choice([
        "This guidance is intended for Retention Specialists.",
        "This document is used by Customer Experience operations.",
        "This guidance applies to NovaCart consumer accounts.",
        "This document should be read with related channel and eligibility rules.",
    ])

    paragraphs = [
        f"# {rng.choice(cfg['titles'])}",
        "",
        "## Purpose",
        terminology_variant(
            rng,
            f"This {doc_type.lower().replace('_', ' ')} explains {topic} for NovaCart customer operations."
        ),
        "",
        "## Core guidance",
        terminology_variant(rng, rule),
        "",
        "## Evidence expectations",
        exception,
        "",
        "## Decision example",
        (
            "A specialist should compare the documented rule with the customer's actual evidence before "
            "making a recommendation. For example, a recent service failure may explain a decline that would "
            "otherwise look like disengagement. The rule should guide the decision, but it should not replace "
            "the underlying customer facts."
        ),
        "",
        "## Exceptions and escalation",
        (
            "If the available evidence falls outside the documented rule, conflicts with another approved "
            "source, or depends on an undocumented exception, the specialist should record the uncertainty "
            "and escalate for review rather than inventing a policy."
        ),
        "",
        "## Source-use guidance",
        (
            "Current approved policies take precedence over drafts, historical versions, FAQs, and informal "
            "operating guidance. Superseded material may be useful for audit history but should not control "
            "a current customer decision."
        ),
        "",
        "## Operational note",
        source_note,
    ]

    if status == "INCOMPLETE":
        paragraphs.extend([
            "",
            "## Known limitation",
            "This document is incomplete. A referenced exception matrix has not been included in this version.",
        ])

    if status == "DRAFT":
        paragraphs.extend([
            "",
            "## Draft notice",
            "This document is under review and should not override a current approved policy.",
        ])

    if status == "SUPERSEDED":
        paragraphs.extend([
            "",
            "## Status notice",
            "This version has been superseded. It is retained for historical retrieval and freshness testing.",
        ])

    # Add controlled lexical overlap.
    if rng.random() < 0.30:
        paragraphs.extend([
            "",
            "## Related concepts",
            "Related terms may include at-risk customer, customer save decision, intervention review, "
            "service escalation, evidence-backed recommendation, and contact suppression.",
        ])

    return "\n".join(paragraphs) + "\n"


def write_doc(path, metadata, content):
    frontmatter = ["---"]
    for k, v in metadata.items():
        frontmatter.append(f"{k}: {json.dumps(v)}")
    frontmatter.append("---")
    path.write_text("\n".join(frontmatter) + "\n\n" + content, encoding="utf-8")


def main():
    args = parse_args()
    rng = random.Random(args.seed)

    if args.output_dir.exists():
        shutil.rmtree(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    manifest_rows = []
    family_counts = Counter()
    status_counts = Counter()
    type_counts = Counter()

    for i in range(1, args.documents + 1):
        family = choose_family(rng)
        cfg = FAMILIES[family]
        doc_type = weighted_choice(rng, DOC_TYPES)
        status = weighted_choice(rng, STATUSES)
        topic = rng.choice(cfg["topics"])
        title = rng.choice(cfg["titles"])
        version = rng.choice(["1.0", "1.1", "2.0", "2.1", "3.0"])
        effective, reviewed, superseded_by = effective_dates(rng, status)

        doc_id = f"KB-{i:05d}"
        filename = f"{doc_id.lower()}-{slugify(title)}.md"
        family_dir = args.output_dir / family
        family_dir.mkdir(parents=True, exist_ok=True)

        metadata = {
            "document_id": doc_id,
            "title": title,
            "family": family,
            "document_type": doc_type,
            "status": status,
            "version": version,
            "effective_date": effective,
            "last_reviewed_date": reviewed,
            "author_team": rng.choice(AUTHOR_TEAMS),
            "authority": "APPROVED" if status == "CURRENT" and doc_type == "POLICY" else "REFERENCE",
            "topic": topic,
        }

        content = policy_content(rng, family, doc_type, status, topic, version)
        write_doc(family_dir / filename, metadata, content)

        family_counts[family] += 1
        status_counts[status] += 1
        type_counts[doc_type] += 1

        manifest_rows.append({
            **metadata,
            "relative_path": str((family_dir / filename).relative_to(args.output_dir)),
        })

    gaps_dir = args.output_dir / "_truth"
    gaps_dir.mkdir(parents=True, exist_ok=True)
    (gaps_dir / "known_knowledge_gaps.json").write_text(
        json.dumps(KNOWN_GAPS, indent=2),
        encoding="utf-8",
    )

    manifest = {
        "seed": args.seed,
        "documents": args.documents,
        "family_counts": dict(family_counts),
        "status_counts": dict(status_counts),
        "document_type_counts": dict(type_counts),
        "known_gap_count": len(KNOWN_GAPS),
        "documents_manifest": manifest_rows,
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    print(json.dumps({
        "documents": args.documents,
        "family_counts": dict(family_counts),
        "status_counts": dict(status_counts),
        "document_type_counts": dict(type_counts),
        "known_gap_count": len(KNOWN_GAPS),
        "output_dir": str(args.output_dir),
    }, indent=2))


if __name__ == "__main__":
    main()
