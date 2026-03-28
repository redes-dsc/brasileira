"""Curador da homepage com ciclo periódico e atualização atômica."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from curador_homepage.acf_applicator import ACFAplicator
from curador_homepage.compositor import HomepageCompositor
from curador_homepage.layout_manager import LayoutManager
from curador_homepage.scorer import editorial_score, objective_score
from shared.kafka_client import KafkaClient
from shared.memory import MemoryManager

logger = logging.getLogger(__name__)

TOPIC_ARTICLE_PUBLISHED = "article-published"
TOPIC_BREAKING_CANDIDATE = "breaking-candidate"
TOPIC_HOMEPAGE_UPDATES = "homepage-updates"


class CuradorHomepageAgent:
    """Agente de curadoria da homepage V3."""

    def __init__(
        self,
        router,
        wp_client,
        kafka_client=None,
        redis_client=None,
        db_pool=None,
        memory: Optional[MemoryManager] = None,
    ):
        self.router = router
        self.wp_client = wp_client
        self.kafka = kafka_client
        self.redis = redis_client
        self.db_pool = db_pool
        self.memory = memory or MemoryManager(redis_client=redis_client, db_pool=db_pool)
        self.layout_manager = LayoutManager()
        self.compositor = HomepageCompositor()
        self.aplicator = ACFAplicator()

    async def coletar_candidatos(self, per_page: int = 50) -> list[dict[str, Any]]:
        """Coleta artigos recentes publicados no WordPress."""

        items = await self.wp_client.get(
            f"/wp-json/wp/v2/posts?status=publish&per_page={per_page}&orderby=date&order=desc&_embed=1"
        )
        if not isinstance(items, list):
            return []

        out: list[dict[str, Any]] = []
        for post in items:
            out.append(
                {
                    "post_id": int(post.get("id", 0)),
                    "titulo": post.get("title", {}).get("rendered", ""),
                    "editoria": str(post.get("slug", "ultimas_noticias")),
                    "urgencia": post.get("meta", {}).get("urgencia", "normal"),
                    "date_gmt": post.get("date_gmt", ""),
                    "fonte_tier": int(post.get("meta", {}).get("fonte_tier", 2)),
                }
            )
        return [x for x in out if x["post_id"] > 0]

    async def executar_ciclo(self, breaking_candidate: dict[str, Any] | None = None) -> dict[str, Any]:
        """Executa ciclo completo de curadoria e publica evento de atualização."""

        lock_key = "homepage:lock"
        if self.redis is not None:
            acquired = await self.redis.set(lock_key, "1", ex=600, nx=True)
            if not acquired:
                raise RuntimeError("Ciclo de homepage já em execução")

        try:
            ciclo_id = str(uuid.uuid4())
            candidatos = await self.coletar_candidatos()

            base_scores = {c["post_id"]: objective_score(c) for c in candidatos}
            llm_scores = await editorial_score(self.router, candidatos) if candidatos else {}

            ranked: list[dict[str, Any]] = []
            for c in candidatos:
                pid = c["post_id"]
                c["score_objetivo"] = base_scores.get(pid, 0.0)
                c["score_editorial"] = llm_scores.get(pid, 0.0)
                c["score_final"] = round(c["score_objetivo"] + c["score_editorial"], 2)
                ranked.append(c)
            ranked.sort(key=lambda x: x["score_final"], reverse=True)

            decision = self.layout_manager.decidir(ranked, breaking_candidate=breaking_candidate)
            composicao = self.compositor.compor(
                ranked=ranked,
                layout=decision.layout,
                breaking_post_id=decision.breaking_post_id,
            )
            timestamp = datetime.now(timezone.utc).isoformat()
            composicao["timestamp"] = timestamp
            composicao["ciclo_id"] = ciclo_id

            apply_result = await self.aplicator.aplicar_atomico(self.wp_client, composicao)

            event = {
                "tipo": "homepage_refresh",
                "layout": decision.layout,
                "manchete_id": composicao.get("manchete_principal"),
                "ciclo_id": ciclo_id,
                "timestamp": timestamp,
            }
            if self.kafka is not None:
                await self.kafka.send(TOPIC_HOMEPAGE_UPDATES, event, key=ciclo_id)

            await self.memory.add_episodic(
                "curador_homepage",
                {
                    "ciclo_id": ciclo_id,
                    "layout": decision.layout,
                    "candidatos": len(candidatos),
                    "changed_fields": apply_result.get("changed_fields", []),
                },
            )
            if self.redis is not None:
                await self.memory.set_working(
                    "curador_homepage",
                    f"ciclo:{ciclo_id}",
                    {
                        "event": event,
                        "changed_fields": apply_result.get("changed_fields", []),
                    },
                )
                await self.redis.hincrby("curador:stats:hoje", "ciclos", 1)

            logger.info(
                "[CuradorHomepage] ciclo=%s layout=%s candidatos=%s",
                ciclo_id,
                decision.layout,
                len(candidatos),
            )
            return {
                "ciclo_id": ciclo_id,
                "layout": decision.layout,
                "updated": apply_result.get("updated", False),
                "changed_fields": apply_result.get("changed_fields", []),
            }
        finally:
            if self.redis is not None:
                await self.redis.delete(lock_key)

    async def consumir_breaking(self, shutdown: Optional[asyncio.Event] = None) -> None:
        """Consome `breaking-candidate` e força ciclo com prioridade, com manual commit."""

        if self.kafka is None:
            raise RuntimeError("KafkaClient é obrigatório para consumer breaking")
        consumer = self.kafka.build_consumer(TOPIC_BREAKING_CANDIDATE, "curador-homepage-breaking")
        await consumer.start()
        logger.info("Consumer breaking-candidate iniciado")
        try:
            while shutdown is None or not shutdown.is_set():
                batch = await consumer.getmany(timeout_ms=1000, max_records=5)
                if not batch:
                    continue
                for _tp, messages in batch.items():
                    for msg in messages:
                        try:
                            await self.executar_ciclo(breaking_candidate=msg.value)
                        except Exception:
                            logger.exception(
                                "Falha ao processar breaking candidate: %s",
                                (msg.value or {}).get("titulo", "?")[:60],
                            )
                await KafkaClient.commit_safe(consumer)
        finally:
            await consumer.stop()
            logger.info("Consumer breaking-candidate encerrado")
