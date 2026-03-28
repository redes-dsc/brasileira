"""Estimativa de custo por chamada LLM."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ModelPricing:
    input_per_million: float
    output_per_million: float


PRICING_USD_PER_MILLION: dict[str, ModelPricing] = {
    # PREMIUM
    "claude-sonnet-4-6": ModelPricing(3.0, 15.0),
    "claude-opus-4.6": ModelPricing(15.0, 75.0),
    "gpt-5.4": ModelPricing(2.5, 15.0),
    "gpt-5.2": ModelPricing(2.0, 10.0),
    "gemini-3.1-pro-preview": ModelPricing(2.0, 12.0),
    "gemini-2.5-pro": ModelPricing(1.25, 10.0),
    "grok-4": ModelPricing(3.0, 15.0),
    "sonar-pro": ModelPricing(3.0, 15.0),
    # PADRAO
    "gpt-4.1-mini": ModelPricing(0.2, 0.8),
    "gpt-5.4-mini": ModelPricing(0.4, 1.6),
    "gemini-2.5-flash": ModelPricing(0.15, 0.6),
    "grok-4-1-fast-reasoning": ModelPricing(1.0, 5.0),
    "deepseek-chat": ModelPricing(0.28, 0.42),
    "qwen3.5-plus": ModelPricing(0.3, 0.9),
    "claude-haiku-4-5": ModelPricing(0.8, 4.0),
    # ECONOMICO
    "qwen3.5-flash": ModelPricing(0.07, 0.26),
    "gemini-2.5-flash-lite": ModelPricing(0.05, 0.15),
    "gpt-4.1-nano": ModelPricing(0.05, 0.2),
    "gpt-5.4-nano": ModelPricing(0.08, 0.3),
    "grok-4-1-fast-non-reasoning": ModelPricing(0.5, 2.0),
    "qwen-turbo": ModelPricing(0.05, 0.15),
}


def estimate_cost_usd(model: str, tokens_in: Optional[int], tokens_out: Optional[int]) -> Optional[float]:
    """Estima custo USD para um par input/output tokens."""
    if tokens_in is None or tokens_out is None:
        return None
    pricing = PRICING_USD_PER_MILLION.get(model)
    if pricing is None:
        return None
    return (tokens_in / 1_000_000) * pricing.input_per_million + (
        tokens_out / 1_000_000
    ) * pricing.output_per_million
