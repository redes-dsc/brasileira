"""Análise de cobertura editorial."""

from __future__ import annotations

from .schemas import CategoryMetrics


class CoverageAnalyzer:
    """Computa peso editorial com base em cobertura recente."""

    async def weights_from_metrics(self, metrics: list[CategoryMetrics]) -> dict[str, float]:
        weights: dict[str, float] = {}
        for item in metrics:
            deficit = 1.0 - item.score_cobertura
            weights[item.categoria] = max(0.5, min(2.0, 1.0 + deficit))
        return weights
