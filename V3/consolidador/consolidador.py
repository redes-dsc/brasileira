"""Consolidador V3 com roteamento 0/1/2+ e integração Kafka/WP."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from consolidador.merger import Merger
from consolidador.rewriter import Rewriter
from consolidador.topic_detector import TopicDetector
from shared.kafka_client import KafkaClient
from shared.memory import MemoryManager

logger = logging.getLogger(__name__)

TOPIC_CONSOLIDACAO = "consolidacao"
TOPIC_PAUTAS_GAP = "pautas-gap"
DLQ_TOPIC = "dlq-articles"


class ConsolidacaoAction(StrEnum):
    """Ações possíveis para o roteamento editorial."""

    ACIONAR_REPORTER = "acionar_reporter"
    REESCREVER = "reescrever"
    CONSOLIDAR = "consolidar"


@dataclass(slots=True)
class ConsolidacaoResultado:
    """Resultado do processamento de um tema."""

    tema_id: str
    acao: ConsolidacaoAction
    post_id: int | None


class ConsolidadorAgent:
    """Agente de consolidação editorial com decisão determinística."""

    def __init__(self, router, wp_client, kafka_client=None, redis_client=None, db_pool=None):
        self.router = router
        self.wp_client = wp_client
        self.kafka = kafka_client
        self.redis = redis_client
        self.memory = MemoryManager(redis_client=redis_client, db_pool=db_pool)
        self.detector = TopicDetector()
        self.rewriter = Rewriter()
        self.merger = Merger()
        self._running = True

    def stop(self) -> None:
        """Sinaliza encerramento gracioso do loop de consumo."""
        self._running = False

    @staticmethod
    def decidir_acao(num_materias_proprias: int) -> ConsolidacaoAction:
        """Regra inviolável 0/1/2+ (sem threshold de 3)."""

        if num_materias_proprias <= 0:
            return ConsolidacaoAction.ACIONAR_REPORTER
        if num_materias_proprias == 1:
            return ConsolidacaoAction.REESCREVER
        return ConsolidacaoAction.CONSOLIDAR

    async def processar_evento(self, evento: dict[str, Any]) -> ConsolidacaoResultado:
        """Processa evento do tópico `consolidacao`."""

        tema_id = str(evento["tema_id"])
        tema = evento.get("tema_descricao", tema_id)
        materias = list(evento.get("materias_proprias", []))
        concorrentes = list(evento.get("artigos_concorrentes", []))
        keywords = list(evento.get("palavras_chave", []))

        lock_key = f"consolidador:lock:{tema_id}"
        if self.redis is not None:
            acquired = await self.redis.set(lock_key, "1", ex=600, nx=True)
            if not acquired:
                raise RuntimeError(f"Tema {tema_id} já em processamento")

        try:
            relacionados = [
                m
                for m in materias
                if self.detector.related_score(keywords, f"{m.get('titulo', '')} {m.get('resumo', '')}") >= 0.2
            ]
            acao = self.decidir_acao(len(relacionados))

            if acao == ConsolidacaoAction.ACIONAR_REPORTER:
                payload = {
                    "tema_id": tema_id,
                    "tema": tema,
                    "urgencia": evento.get("urgencia", "normal"),
                    "tipo": "cobertura_nova",
                    "palavras_chave": keywords,
                    "urls_referencia": [a.get("url") for a in concorrentes if a.get("url")],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                if self.kafka is None:
                    raise RuntimeError("KafkaClient é obrigatório para enviar pautas-gap")
                await self.kafka.send(TOPIC_PAUTAS_GAP, payload, key=tema_id)
                post_id = None
            elif acao == ConsolidacaoAction.REESCREVER:
                conteudo = await self.rewriter.reescrever(self.router, tema, relacionados[0], concorrentes)
                created = await self._publicar(conteudo, evento)
                post_id = int(created["id"])
            else:
                conteudo = await self.merger.consolidar(self.router, tema, relacionados, concorrentes)
                created = await self._publicar(conteudo, evento)
                post_id = int(created["id"])

            await self.memory.add_episodic(
                "consolidador",
                {
                    "tema_id": tema_id,
                    "acao": acao.value,
                    "num_materias": len(relacionados),
                    "post_id": post_id,
                },
            )
            if self.redis is not None:
                await self.memory.set_working(
                    "consolidador",
                    f"tema:{tema_id}",
                    {
                        "evento": evento,
                        "acao": acao.value,
                        "post_id": post_id,
                    },
                )
                await self.redis.hincrby("consolidador:stats:hoje", "temas_processados", 1)

            logger.info("[Consolidador] tema=%s acao=%s post_id=%s", tema_id, acao.value, post_id)
            return ConsolidacaoResultado(tema_id=tema_id, acao=acao, post_id=post_id)
        finally:
            if self.redis is not None:
                await self.redis.delete(lock_key)

    async def _publicar(self, conteudo: dict[str, Any], evento: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "title": conteudo.get("titulo", evento.get("tema_descricao", "Consolidação")),
            "content": conteudo.get("corpo", ""),
            "excerpt": conteudo.get("resumo", ""),
            "status": "publish",
            "categories": [int(evento.get("categoria_wp_id", 17))],
        }
        return await self.wp_client.post("/wp-json/wp/v2/posts", json=payload)

    async def consumir(self) -> None:
        """Loop contínuo de consumo do tópico consolidacao com batch processing."""

        if self.kafka is None:
            raise RuntimeError("KafkaClient é obrigatório para consumir consolidação")
        consumer = self.kafka.build_consumer(TOPIC_CONSOLIDACAO, "consolidador-consumers")
        await consumer.start()
        logger.info("Consolidador consumer iniciado: %s", TOPIC_CONSOLIDACAO)
        try:
            while self._running:
                batch = await consumer.getmany(timeout_ms=1000, max_records=20)
                if not batch:
                    continue
                for tp, messages in batch.items():
                    for msg in messages:
                        try:
                            await self.processar_evento(msg.value)
                        except Exception:
                            logger.error(
                                "Falha ao processar evento consolidacao: tema=%s",
                                msg.value.get("tema_id", "?") if isinstance(msg.value, dict) else "?",
                                exc_info=True,
                            )
                            try:
                                await self.kafka.send(DLQ_TOPIC, {
                                    "original": msg.value,
                                    "error": "consolidador_processing_failed",
                                    "source_topic": TOPIC_CONSOLIDACAO,
                                })
                            except Exception:
                                logger.error("Falha ao enviar para DLQ", exc_info=True)
                await KafkaClient.commit_safe(consumer)
        finally:
            await consumer.stop()
