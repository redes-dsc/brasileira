"""Orquestrador do Monitor de Sistema."""

from __future__ import annotations

import logging
from typing import Union

from .adaptive_polling import AdaptivePolling
from .config import MonitorSistemaConfig
from .coverage_checker import CoverageChecker
from .focas import FocasController
from .health_checker import HealthChecker
from .throughput_tracker import ThroughputTracker

logger = logging.getLogger(__name__)


class MonitorSistema:
    """Monitora throughput/cobertura e aplica FOCAS sem bloqueio do pipeline."""

    def __init__(self, redis_client=None, config: MonitorSistemaConfig | None = None):
        self.redis = redis_client
        self.config = config or MonitorSistemaConfig()
        self.throughput = ThroughputTracker(self.config)
        self.coverage = CoverageChecker(self.config)
        self.health = HealthChecker()
        self.focas = FocasController(AdaptivePolling(self.config))

    async def run_cycle(
        self,
        published_events: Union[list[dict], int] = 0,
        fontes: list[dict] | None = None,
        custo_hora: float = 0.0,
    ) -> dict:
        # published_events pode ser int (contagem) ou list (eventos individuais)
        if isinstance(published_events, list):
            artigos_ultima_hora = len(published_events)
            published_events_24h = published_events
        else:
            artigos_ultima_hora = int(published_events)
            published_events_24h = []

        if fontes is None:
            fontes = []

        throughput_status = await self.throughput.evaluate(artigos_ultima_hora)
        coverage_snapshot = await self.coverage.snapshot(published_events_24h)
        health_status = await self.health.summarize(throughput_status, cost_usd_hour=custo_hora)

        focas_updates = [await self.focas.decide(fonte, throughput_status.nivel) for fonte in fontes]

        if self.redis is not None:
            await self.redis.set("monitor_sistema:throughput:nivel", throughput_status.nivel, ex=300)
            for item in coverage_snapshot:
                await self.redis.set(f"monitor_sistema:coverage:{item.categoria}", str(item.volume_24h), ex=900)
            for update in focas_updates:
                await self.redis.hset(
                    f"focas:fonte:{update.fonte_id}",
                    mapping={
                        "polling_interval_min": update.polling_interval_min,
                        "tier": update.tier,
                        "ativa": "1",
                    },
                )
                await self.redis.expire(f"focas:fonte:{update.fonte_id}", 86400)

        logger.info("Monitor sistema ciclo concluído: throughput=%s focas_updates=%d", throughput_status.nivel, len(focas_updates))
        return {
            "throughput": throughput_status.model_dump(mode="json"),
            "coverage": [item.model_dump(mode="json") for item in coverage_snapshot],
            "health": health_status,
            "focas_updates": [item.model_dump(mode="json") for item in focas_updates],
        }
