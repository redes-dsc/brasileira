"""Feed Scheduler para distribuir assignments de fontes via Kafka."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from shared.kafka_client import KafkaClient

logger = logging.getLogger(__name__)

TOPIC_ASSIGNMENTS = "fonte-assignments"
DEFAULT_CYCLE_INTERVAL = 1800


class FeedScheduler:
    """Distribui fontes para workers de forma resiliente."""

    def __init__(
        self,
        kafka_bootstrap: str,
        db_pool,
        health_tracker,
        cycle_interval: int = DEFAULT_CYCLE_INTERVAL,
    ):
        self.kafka = KafkaClient(kafka_bootstrap)
        self.db_pool = db_pool
        self.health_tracker = health_tracker
        self.cycle_interval = cycle_interval
        self._running = True

    async def start(self) -> None:
        await self.kafka.start_producer()

    async def stop(self) -> None:
        self._running = False
        await self.kafka.stop_producer()

    async def load_all_sources(self) -> list[dict]:
        """Carrega todas as fontes ativas."""

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, nome, url, tipo, tier, config_scraper, polling_interval_min,
                       ultimo_sucesso, ultimo_erro, ativa
                FROM fontes
                WHERE ativa = TRUE
                ORDER BY CASE tier
                    WHEN 'vip' THEN 1
                    WHEN 'padrao' THEN 2
                    WHEN 'secundario' THEN 3
                    ELSE 4 END,
                    ultimo_sucesso ASC NULLS FIRST
                """
            )
        return [dict(row) for row in rows]

    def _should_process_source(self, source: dict) -> bool:
        if source.get("tier") == "vip":
            return True
        if source.get("ultimo_sucesso") is None:
            return True

        health = self.health_tracker.get_source_health(source["id"]) if self.health_tracker else None
        interval = int(source.get("polling_interval_min") or 30)
        if health and health.consecutive_failures > 0:
            backoff_factor = min(2 ** health.consecutive_failures, 12)
            interval = min(interval * backoff_factor, 360)

        elapsed_minutes = (
            datetime.now(timezone.utc) - source["ultimo_sucesso"]
        ).total_seconds() / 60
        return elapsed_minutes >= interval

    async def schedule_cycle(self) -> None:
        """Executa um ciclo de agendamento: query DB, produce to Kafka, done."""

        sources = await self.load_all_sources()
        to_process = [source for source in sources if self._should_process_source(source)]

        sent = 0
        for source in to_process:
            if not self._running:
                break
            assignment = {
                "fonte_id": source["id"],
                "nome": source["nome"],
                "url": source["url"],
                "tipo": source["tipo"],
                "tier": source["tier"],
                "config_scraper": source.get("config_scraper"),
                "polling_interval_min": source.get("polling_interval_min", 30),
                "priority": "high" if source.get("tier") == "vip" else "normal",
                "scheduled_at": datetime.now(timezone.utc).isoformat(),
                "retry": False,
            }
            await self.kafka.send(TOPIC_ASSIGNMENTS, assignment, key=str(source["id"]))
            sent += 1

        logger.info("Ciclo agendado: %d/%d fontes enviadas para workers", sent, len(sources))

    async def run_forever(self) -> None:
        await self.start()
        while self._running:
            try:
                await self.schedule_cycle()
                await asyncio.sleep(self.cycle_interval)
            except Exception:
                logger.exception("Erro no scheduler")
                await asyncio.sleep(60)
