from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TokenPricing:
    input_per_million: float
    cached_input_per_million: float
    output_per_million: float


# Verified against OpenAI's public model/pricing documentation on 2026-08-14.
# Keep pricing explicit and version-controlled because prices can change.
MODEL_PRICING = {
    "gpt-5.6-luna": TokenPricing(
        input_per_million=1.00,
        cached_input_per_million=0.10,
        output_per_million=6.00,
    ),
    "gpt-5.6-terra": TokenPricing(
        input_per_million=2.50,
        cached_input_per_million=0.25,
        output_per_million=15.00,
    ),
    "gpt-5.6-sol": TokenPricing(
        input_per_million=5.00,
        cached_input_per_million=0.50,
        output_per_million=30.00,
    ),
    # Alias currently routes to Sol, but keeping the explicit alias here makes
    # local reports understandable if it is used.
    "gpt-5.6": TokenPricing(
        input_per_million=5.00,
        cached_input_per_million=0.50,
        output_per_million=30.00,
    ),
}


def estimate_text_cost_usd(
    model: str,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
) -> float | None:
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        return None

    uncached = max(0, input_tokens - cached_input_tokens)
    cost = (
        uncached * pricing.input_per_million
        + cached_input_tokens * pricing.cached_input_per_million
        + output_tokens * pricing.output_per_million
    ) / 1_000_000
    return round(cost, 8)
