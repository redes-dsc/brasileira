"""Observer estratégico de fim de pipeline."""

from __future__ import annotations

import logging
from typing import Any, Optional

from shared.kafka_client import KafkaClient

from .config import EditorChefeConfig
from .coverage_analyzer import CoverageAnalyzer
from .gap_detector import GapDetector
from .metrics_collector import MetricsCollector

logger = logging.getLogger(__name__)


class EditorChefeObserver:
    """Componente analítico que observa e ajusta prioridades, sem bloquear."""

    def __init__(
        self,
        kafka_client: KafkaClient,
        redis_client: Optional[Any] = None,
        config: Optional[EditorChefeConfig] = None,
        wp_client: Optional[Any] = None,
        db_pool: Optional[Any] = None,
    ):
        self.kafka = kafka_client
        self.redis = redis_client
        self.config = config or EditorChefeConfig()
        self.wp_client = wp_client
        self.db_pool = db_pool
        self.collector = MetricsCollector(wp_client=wp_client)
        self.coverage = CoverageAnalyzer()
        self.gaps = GapDetector(self.config)

    async def run_cycle(self, published_events: Optional[list[dict]] = None) -> dict[str, float]:
        metrics = await self.collector.collect(published_events)
        weights = await self.coverage.weights_from_metrics(metrics)

        if self.redis is not None:
            for categoria, peso in weights.items():
                key = f"{self.config.redis_weight_prefix}:{categoria}"
                await self.redis.set(key, str(peso), ex=3600)

        gaps = await self.gaps.detect(metrics, weights)
        for gap in gaps:
            await self.kafka.send(
                self.config.kafka_topic_gaps,
                gap.model_dump(mode="json"),
                key=gap.urgencia,
            )

        logger.info("Editor-chefe ciclo analítico: categorias=%d gaps=%d", len(weights), len(gaps))
        return weights
