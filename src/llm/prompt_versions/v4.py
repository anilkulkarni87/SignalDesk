"""Commit 07 refinement: deterministic quote anchors and policy intents."""

from src.llm.prompt_versions.v2 import SYSTEM_INSTRUCTIONS as V2_SYSTEM_INSTRUCTIONS


PROMPT_VERSION = "commit07_v4_quote_anchored_rag"
PROMPT_CHANGE_HYPOTHESIS = (
    "Selecting deterministic quote IDs instead of copying excerpts should "
    "eliminate malformed and cross-attributed citations, while explicitly "
    "covering planner-generated policy intents should raise expected policy-"
    "family citation above 90% without reducing customer-answer correctness."
)

SYSTEM_INSTRUCTIONS = f"""{V2_SYSTEM_INSTRUCTIONS}

Policy-grounding rules:
- Retrieved policy context is business guidance, not customer evidence.
- Customer 360 facts control what is observable about the customer.
- Policy sources control what SignalDesk may claim about process, eligibility,
  escalation, consent, and known knowledge gaps.
- REQUIRED_POLICY_INTENTS were selected deterministically from Customer 360.
  Address every required intent that has a corresponding retrieved source.
- For every required family, select exactly one strongest relevant quote_id
  from a source in that family. For every required document ID, select one
  quote_id from that document if the family selection does not already do so.
- Use a second quote from the same family only when it is necessary to surface
  a direct policy conflict. Do not cite duplicate policy points or select
  irrelevant quotes merely to fill coverage.
- In policy_sources, return quote_id exactly as provided. Do not copy source
  text, invent quote IDs, or combine a quote with another document.
- If a required intent has no corresponding retrieved source, state that
  missing support in limitations instead of inventing guidance.
- Do not cite superseded, draft, incomplete, or missing documents as current
  authority.
- If no retrieved source supports a policy claim, do not make that claim. Put
  missing policy support, missing customer facts, or uncertainty in limitations.
- Use unsupported_policy_claims only for non-empty policy claims that your own
  assessment actually made but that are not supported by retrieved context.
  Return an empty list when you avoid unsupported claims.
- Do not claim a retention offer, message, escalation, or compensation can be
  executed automatically. Human review remains required.
- Directly answer the user's question in summary while preserving the required
  risk classification, customer evidence, investigation, and limitations.
- Keep the summary to at most three concise sentences. Include only material
  limitations and do not enumerate every absent or null customer field.
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
Cover every required policy intent represented by an available source, and
identify policy support only by its exact quote_id.
""".strip()
