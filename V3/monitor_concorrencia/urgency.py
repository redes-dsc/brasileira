"""Cálculo de urgência para sinais concorrenciais."""

from __future__ import annotations

from .schemas import CoverageResult


class UrgencyScorer:
    """Define nível de urgência para roteamento tático."""

    async def score(self, result: CoverageResult) -> str:
        if result.status == "gap" and result.similaridade < 0.2:
            return "critico"
        if result.status == "gap":
            return "alto"
        if result.status == "parcial":
            return "medio"
        return "baixo"
