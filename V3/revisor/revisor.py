"""Revisor: post-publicação QA com LLM PADRAO. NUNCA rejeita, corrige in-place via PATCH."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from shared.schemas import LLMRequest

logger = logging.getLogger(__name__)

REVISION_LOCK_TTL = 120  # seconds


class RevisorAgent:
    """Revisa artigos publicados e aplica correções in-place."""

    def __init__(self, wp_client, router, redis=None, pg_pool=None, kafka=None):
        self.wp = wp_client
        self.router = router
        self.redis = redis
        self.pg_pool = pg_pool
        self.kafka = kafka

    async def processar_evento(self, event: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Processa evento article-published: revisa e corrige."""
        wp_post_id = event.get("wp_post_id")
        if not wp_post_id:
            return None

        # Lock distribuído para idempotência
        if self.redis:
            lock_key = f"revisor:lock:{wp_post_id}"
            acquired = await self.redis.set(lock_key, "1", ex=REVISION_LOCK_TTL, nx=True)
            if not acquired:
                logger.debug("Post %d já em revisão, pulando", wp_post_id)
                return None  # Skip gracefully, NÃO raise

        logger.info("Revisando post %d", wp_post_id)

        # 1. Carregar post do WordPress
        try:
            post = await self.wp.get(f"/wp-json/wp/v2/posts/{wp_post_id}")
        except Exception:
            logger.error("Falha ao carregar post %d do WordPress", wp_post_id, exc_info=True)
            return None

        if isinstance(post, list):
            post = post[0] if post else {}

        titulo = post.get("title", {}).get("rendered", "")
        conteudo = post.get("content", {}).get("rendered", "")
        resumo = post.get("excerpt", {}).get("rendered", "")

        if not conteudo:
            logger.warning("Post %d sem conteúdo, pulando revisão", wp_post_id)
            return None

        # 2. Revisão completa via LLM PADRAO (gramática + estilo + SEO)
        corrections = await self._review_with_llm(titulo, conteudo, resumo)

        if not corrections or not corrections.get("has_corrections"):
            logger.info("Post %d sem correções necessárias", wp_post_id)
            return {"wp_post_id": wp_post_id, "corrections": 0}

        # 3. Aplicar correções via PATCH (NUNCA rejeita — Regra #10)
        patch_data: dict[str, Any] = {}
        if corrections.get("titulo_corrigido") and corrections["titulo_corrigido"] != titulo:
            patch_data["title"] = corrections["titulo_corrigido"]
        if corrections.get("conteudo_corrigido") and corrections["conteudo_corrigido"] != conteudo:
            patch_data["content"] = corrections["conteudo_corrigido"]
        if corrections.get("resumo_corrigido") and corrections["resumo_corrigido"] != resumo:
            patch_data["excerpt"] = corrections["resumo_corrigido"]

        if patch_data:
            try:
                await self.wp.patch(f"/wp-json/wp/v2/posts/{wp_post_id}", json=patch_data)
                logger.info("Post %d corrigido: %d campos", wp_post_id, len(patch_data))
            except Exception:
                logger.error("Falha ao aplicar PATCH no post %d", wp_post_id, exc_info=True)

        # 4. Registrar revisão na memória episódica
        if self.pg_pool:
            try:
                from shared.memory import MemoryManager
                memory = MemoryManager(db_pool=self.pg_pool)
                await memory.add_episodic("revisor", {
                    "wp_post_id": wp_post_id,
                    "corrections_applied": len(patch_data),
                    "corrections_detail": corrections.get("corrections_list", []),
                })
            except Exception:
                pass

        return {"wp_post_id": wp_post_id, "corrections": len(patch_data)}

    async def _review_with_llm(self, titulo: str, conteudo: str, resumo: str) -> Optional[dict[str, Any]]:
        """Revisão via LLM PADRAO: gramática, estilo, SEO."""
        prompt = f"""Você é revisor do portal brasileira.news.
Revise o artigo abaixo e retorne APENAS as correções necessárias.

REGRAS:
- Corrija erros gramaticais (concordância, regência, crase, pontuação)
- Corrija estilo (voz passiva → ativa, frases longas → curtas)
- Verifique SEO (título max 65 chars, meta description max 155 chars)
- NÃO altere fatos, dados, nomes, datas ou citações
- Se não há correções, retorne has_corrections: false

TÍTULO: {titulo}
CONTEÚDO:
{conteudo[:3000]}
RESUMO: {resumo}

Responda em JSON:
{{"has_corrections": true/false, "titulo_corrigido": "...", "conteudo_corrigido": "...", "resumo_corrigido": "...", "corrections_list": ["descrição da correção 1", ...]}}"""

        try:
            request = LLMRequest(
                task_type="revisao_texto",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4000,
                temperature=0.2,
            )
            response = await self.router.route_request(request)
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0]
            return json.loads(content)
        except Exception:
            logger.warning("Revisão LLM falhou", exc_info=True)
            return None

    async def consumir(self):
        """Loop de consumo do Kafka."""
        from shared.kafka_client import KafkaClient
        consumer_kafka = KafkaClient(self.kafka.bootstrap_servers if hasattr(self.kafka, 'bootstrap_servers') else "kafka:29092")
        consumer = consumer_kafka.build_consumer("article-published", group_id="revisor-pipeline")
        await consumer.start()
        logger.info("Revisor consumer iniciado")
        try:
            while True:
                batch = await consumer.getmany(timeout_ms=2000, max_records=5)
                for tp, messages in batch.items():
                    for msg in messages:
                        try:
                            await self.processar_evento(msg.value)
                        except Exception:
                            logger.error("Falha ao revisar artigo", exc_info=True)
                if batch:
                    await KafkaClient.commit_safe(consumer)
        finally:
            await consumer.stop()
