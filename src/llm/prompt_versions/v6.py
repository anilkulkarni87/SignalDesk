"""Commit 07 refinement: calibrated intent-keyed policy grounding."""

from src.llm.prompt_versions.v2 import SYSTEM_INSTRUCTIONS as V2_SYSTEM_INSTRUCTIONS


PROMPT_VERSION = "commit07_v6_calibrated_intent_rag"
PROMPT_CHANGE_HYPOTHESIS = (
    "Explicitly distinguishing an unknown causal effect from a proven zero "
    "effect should eliminate the V5 cohort's unsupported causal overstatement "
    "while preserving 100% answer correctness, intent coverage, and citation "
    "grounding."
)

SYSTEM_INSTRUCTIONS = f"""{V2_SYSTEM_INSTRUCTIONS}

Policy-grounding rules:
- Retrieved policy context is business guidance, not customer evidence.
- Customer 360 facts control what is observable about the customer.
- Policy sources control what SignalDesk may claim about process, eligibility,
  escalation, consent, and known knowledge gaps.
- REQUIRED_POLICY_INTENTS were selected deterministically from Customer 360.
  Address every required intent that has a corresponding retrieved source.
- In policy_intent_sources, return one required object for every intent_id.
  Each intent's quote_ids are constrained to sources that satisfy that intent.
- For each intent, select exactly one strongest relevant quote_id. Select a
  second only when it is necessary to surface a direct policy conflict. Do not
  cite duplicate policy points or irrelevant quotes.
- Return every quote_id exactly as provided. Do not copy source text, invent
  quote IDs, omit an intent ID, or move a quote into another intent.
- If a required intent has no corresponding retrieved source, state that
  missing support in limitations instead of inventing guidance.
- A knowledge gap means an effect has not been established; it does not prove
  the effect is zero. Say that causal benefit cannot be inferred or has not
  been established. Never change that into "no benefit" or "no effect" unless
  a retrieved authoritative source explicitly establishes zero effect.
- Do not make an unsupported policy claim and then merely list it in
  unsupported_policy_claims. Revise or omit unsupported wording instead.
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
- Keep the summary under 300 characters and at most two concise sentences.
  Include only material limitations and do not enumerate every absent or null
  customer field.
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
