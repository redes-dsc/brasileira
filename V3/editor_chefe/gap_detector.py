"""Detector de gaps urgentes."""

from __future__ import annotations

from datetime import datetime, timezone

from .config import EditorChefeConfig
from .schemas import CategoryMetrics, GapSignal


class GapDetector:
    """Identifica lacunas e cria sinais para pautas-gap."""

    def __init__(self, config: EditorChefeConfig | None = None):
        self.config = config or EditorChefeConfig()

    async def detect(self, metrics: list[CategoryMetrics], weights: dict[str, float]) -> list[GapSignal]:
        gaps: list[GapSignal] = []
        for item in metrics:
            if item.horas_desde_ultimo > self.config.gap_hours_threshold:
                gaps.append(
                    GapSignal(
                        categoria=item.categoria,
                        urgencia="urgente",
                        motivo="baixa cobertura recente",
                        peso_sugerido=weights[item.categoria],
                        criado_em=datetime.now(timezone.utc),
                    )
                )
        return gaps
