"""Checagem de cobertura por categoria."""

from __future__ import annotations

from collections import Counter

from .config import MonitorSistemaConfig
from .schemas import CoverageSnapshot


class CoverageChecker:
    """Calcula volume por macrocategoria nas últimas 24h."""

    def __init__(self, config: MonitorSistemaConfig):
        self.config = config

    async def snapshot(self, published_events: list[dict]) -> list[CoverageSnapshot]:
        counts = Counter(str(event.get("categoria", "ultimas_noticias")) for event in published_events)
        return [CoverageSnapshot(categoria=cat, volume_24h=counts[cat]) for cat in self.config.categorias]
