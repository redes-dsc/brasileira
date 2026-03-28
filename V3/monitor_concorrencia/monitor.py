"""Orquestrador do monitor de concorrência."""

from __future__ import annotations

import logging

from shared.kafka_client import KafkaClient

from .config import MonitorConcorrenciaConfig
from .gap_analysis import GapAnalyzer
from .portais import PORTAIS_PADRAO
from .scanner import PortalScanner
from .urgency import UrgencyScorer

logger = logging.getLogger(__name__)

_ALLOWED_TOPICS = {"pautas-gap", "consolidacao", "breaking-candidate"}


class MonitorConcorrencia:
    """Escaneia portais, classifica cobertura e roteia alertas."""

    def __init__(self, kafka_client: KafkaClient, config: MonitorConcorrenciaConfig | None = None):
        self.kafka = kafka_client
        self.config = config or MonitorConcorrenciaConfig()
        self.scanner = PortalScanner(self.config)
        self.analyzer = GapAnalyzer(self.config)
        self.urgency = UrgencyScorer()

    async def run_cycle(self, nossos_titulos: list[str]) -> int:
        published = 0
        cluster_counts: dict[str, int] = {}
        pending: list[tuple[dict, str, str]] = []
        for portal in PORTAIS_PADRAO:
            artigos = await self.scanner.scan_portal(
                portal.nome, portal.url, portal.requires_browser, selectors=portal.selectors
            )
            coverage = await self.analyzer.classify(artigos, nossos_titulos=nossos_titulos)
            for artigo, result in zip(artigos, coverage, strict=False):
                urgency = await self.urgency.score(result)
                payload = {
                    "portal": artigo.portal,
                    "titulo": artigo.titulo,
                    "url": artigo.url,
                    "status": result.status,
                    "similaridade": result.similaridade,
                    "urgencia": urgency,
                    "topico_normalizado": result.topico_normalizado,
                }
                cluster = result.topico_normalizado
                cluster_counts[cluster] = cluster_counts.get(cluster, 0) + 1
                pending.append((payload, result.topico_destino, cluster))

        for payload, topic, cluster in pending:
            if cluster_counts.get(cluster, 0) >= self.config.breaking_min_portals:
                topic = self.config.topic_breaking
                payload["breaking_capas"] = cluster_counts[cluster]
            if topic not in _ALLOWED_TOPICS:
                continue
            await self.kafka.send(topic, payload, key=payload["urgencia"])
            published += 1
        logger.info("Monitor concorrência publicou %d mensagens", published)
        return published
