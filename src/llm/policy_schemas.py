from __future__ import annotations

from copy import deepcopy
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from .policy_context import PolicyQuote
from .schemas import CustomerAssessment


QuoteId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=4,
        pattern=r"^Q[0-9]{3}$",
    ),
]
UnsupportedPolicyClaim = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=240,
        pattern=r".*\S.*",
    ),
]


class PolicyIntentSourceSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quote_ids: list[QuoteId] = Field(
        min_length=1,
        max_length=2,
        description=(
            "One strongest quote for this policy intent, plus a second only "
            "when needed to show a direct policy conflict."
        ),
    )
    relevance: str = Field(min_length=1, max_length=240)
    cited_policy_point: str = Field(min_length=1, max_length=240)


class ModelPolicyGroundedAssessment(CustomerAssessment):
    model_config = ConfigDict(extra="forbid")

    policy_intent_sources: dict[str, PolicyIntentSourceSelection] = Field(
        min_length=1,
        max_length=5,
        description=(
            "One required source selection for every policy intent ID."
        ),
    )
    unsupported_policy_claims: list[UnsupportedPolicyClaim] = Field(
        max_length=5,
        description=(
            "Non-empty policy claims included in the assessment that are not "
            "supported by retrieved policy sources. Return an empty list when "
            "the assessment avoids unsupported policy claims."
        ),
    )

    @model_validator(mode="after")
    def quote_ids_are_unique(self):
        quote_ids = [
            quote_id
            for source in self.policy_intent_sources.values()
            for quote_id in source.quote_ids
        ]
        if len(quote_ids) != len(set(quote_ids)):
            raise ValueError(
                "policy_intent_sources must use unique quote IDs"
            )
        return self


class PolicySourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_id: str = Field(pattern=r"^I[0-9]{2}$")
    quote_id: QuoteId
    document_id: str = Field(min_length=1, max_length=80)
    relevance: str = Field(min_length=1, max_length=240)
    cited_policy_point: str = Field(min_length=1, max_length=240)
    supporting_excerpt: str = Field(
        min_length=1,
        max_length=320,
        description=(
            "Exact excerpt resolved deterministically from quote_id."
        ),
    )


class PolicyGroundedAssessment(CustomerAssessment):
    model_config = ConfigDict(extra="forbid")

    policy_sources: list[PolicySourceReference] = Field(
        min_length=1,
        max_length=10,
    )
    unsupported_policy_claims: list[UnsupportedPolicyClaim] = Field(
        max_length=5,
        description=(
            "Non-empty policy claims included in the assessment that are not "
            "supported by retrieved policy sources."
        ),
    )


def resolve_policy_assessment(
    assessment: ModelPolicyGroundedAssessment,
    quotes_by_id: dict[str, PolicyQuote],
    intent_quote_ids: dict[str, list[str]],
) -> PolicyGroundedAssessment:
    expected_intents = set(intent_quote_ids)
    selected_intents = set(assessment.policy_intent_sources)
    if selected_intents != expected_intents:
        raise ValueError(
            "Model policy intent IDs do not match required intent IDs"
        )

    resolved_sources = []
    for intent_id, source in assessment.policy_intent_sources.items():
        allowed_quote_ids = set(intent_quote_ids[intent_id])
        for quote_id in source.quote_ids:
            if quote_id not in allowed_quote_ids:
                raise ValueError(
                    f"Quote ID {quote_id} is not valid for {intent_id}"
                )
            quote = quotes_by_id.get(quote_id)
            if quote is None:
                raise ValueError(
                    f"Model selected unknown policy quote ID {quote_id}"
                )
            resolved_sources.append(PolicySourceReference(
                intent_id=intent_id,
                quote_id=quote_id,
                document_id=quote.document_id,
                relevance=source.relevance,
                cited_policy_point=source.cited_policy_point,
                supporting_excerpt=quote.text,
            ))

    values = assessment.model_dump(exclude={"policy_intent_sources"})
    return PolicyGroundedAssessment(
        **values,
        policy_sources=resolved_sources,
    )


def model_assessment_schema(
    intent_quote_ids: dict[str, list[str]],
) -> dict:
    if not intent_quote_ids:
        raise ValueError("At least one policy intent is required")
    empty_intents = [
        intent_id
        for intent_id, quote_ids in intent_quote_ids.items()
        if not quote_ids
    ]
    if empty_intents:
        raise ValueError(
            "No policy quotes are available for intents: "
            + ", ".join(sorted(empty_intents))
        )

    schema = ModelPolicyGroundedAssessment.model_json_schema()
    selection_schema = schema["$defs"]["PolicyIntentSourceSelection"]
    intent_properties = {}
    for intent_id, quote_ids in intent_quote_ids.items():
        intent_schema = deepcopy(selection_schema)
        intent_schema["properties"]["quote_ids"]["items"]["enum"] = sorted(
            set(quote_ids)
        )
        intent_properties[intent_id] = intent_schema

    schema["properties"]["policy_intent_sources"] = {
        "additionalProperties": False,
        "description": (
            "One required source selection for every policy intent ID."
        ),
        "properties": intent_properties,
        "required": list(intent_properties),
        "type": "object",
    }
    return schema
