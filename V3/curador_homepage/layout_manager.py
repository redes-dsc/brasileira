"""Decisor de layout da homepage (normal/amplo/breaking)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class LayoutDecision:
    """Decisão final de layout."""

    layout: str
    breaking_post_id: int | None = None


class LayoutManager:
    """Decide layout com base em sinais de urgência."""

    def decidir(self, ranked: list[dict], breaking_candidate: dict | None = None) -> LayoutDecision:
        """Retorna decisão determinística de layout."""

        if breaking_candidate and breaking_candidate.get("post_id"):
            return LayoutDecision(layout="breaking", breaking_post_id=int(breaking_candidate["post_id"]))

        if ranked and ranked[0].get("score_final", 0) >= 80:
            return LayoutDecision(layout="amplo")

        return LayoutDecision(layout="normal")
