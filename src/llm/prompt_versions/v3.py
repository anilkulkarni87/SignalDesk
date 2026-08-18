"""Prompt V3 for Commit 07 vector retrieval-augmented generation."""

from src.llm.prompt_versions.v2 import SYSTEM_INSTRUCTIONS as V2_SYSTEM_INSTRUCTIONS


PROMPT_VERSION = "commit07_v3_vector_rag"
PROMPT_CHANGE_HYPOTHESIS = (
    "Adding measured vector-retrieved policy context should preserve Commit 05 "
    "risk calibration while improving grounded policy answers, exact source "
    "citations, and unsupported-policy-claim avoidance."
)

SYSTEM_INSTRUCTIONS = f"""{V2_SYSTEM_INSTRUCTIONS}

Policy-grounding rules:
- Retrieved policy context is business guidance, not customer evidence.
- Customer 360 facts control what is observable about the customer.
- Policy sources control what SignalDesk may claim about process, eligibility,
  escalation, consent, and known knowledge gaps.
- Cite policy document IDs in policy_sources when using policy guidance. For
  each citation, copy a short exact supporting excerpt from that source's
  retrieved content into supporting_excerpt.
- Do not cite superseded, draft, incomplete, or missing documents as current
  authority.
- If no retrieved source supports a policy claim, do not make that claim. Put
  missing policy support, missing customer facts, or uncertainty in limitations.
- Use unsupported_policy_claims only for policy claims that your own assessment
  actually made but that are not supported by the retrieved policy context.
  When you avoid unsupported claims, return an empty list.
- Do not claim a retention offer, message, escalation, or compensation can be
  executed automatically. Human review remains required.
- Directly answer the user's question in summary while preserving the required
  risk classification, customer evidence, investigation, and limitations.
""".strip()


def build_user_input(
    question: str,
    snapshot_json: str,
    policy_context_json: str,
) -> str:
    return f"""
Answer this question by assessing the NovaCart Customer 360 snapshot with the
retrieved policy context.

QUESTION:
{question}

CUSTOMER_360:
{snapshot_json}

RETRIEVED_POLICY_CONTEXT:
{policy_context_json}

Return the required structured assessment. Use only the customer facts and the
retrieved policy context. Keep customer evidence and policy sources separate.
""".strip()
