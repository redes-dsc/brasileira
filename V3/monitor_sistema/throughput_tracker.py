"""Monitor de throughput com SLOs definidos."""

from __future__ import annotations

from .config import MonitorSistemaConfig
from .schemas import ThroughputStatus


class ThroughputTracker:
    """Classifica throughput em saudável/alerta/crítico."""

    def __init__(self, config: MonitorSistemaConfig):
        self.config = config

    async def evaluate(self, artigos_publicados_ultima_hora: int) -> ThroughputStatus:
        aph = float(artigos_publicados_ultima_hora)
        if aph <= self.config.critical_per_hour:
            nivel = "critico"
        elif aph <= self.config.alert_per_hour:
            nivel = "alerta"
        elif aph >= self.config.target_per_hour:
            nivel = "saudavel"
        else:
            nivel = "moderado"
        return ThroughputStatus(artigos_por_hora=aph, nivel=nivel)
