"""Pipeline editorial: extract -> contextualize (RAG) -> write -> SEO -> publish."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from shared.memory import MemoryManager

from .content_extractor import extract_content
from .writer import write_article
from .seo_optimizer import optimize_seo
from .publisher import publish_to_wordpress

logger = logging.getLogger(__name__)


class ReporterAgent:
    """Agente Reporter: extrai, redige, otimiza SEO e publica."""

    def __init__(self, router, wp_client, memory: Optional[MemoryManager] = None, pg_pool=None):
        self.router = router
        self.wp = wp_client
        self.memory = memory
        self.pg_pool = pg_pool

    async def processar(self, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Pipeline completo de produção editorial."""
        titulo = payload.get("titulo", "")
        url = payload.get("url", "")
        url_hash = payload.get("url_hash", hashlib.sha256(url.encode()).hexdigest()[:16])

        logger.info("Reporter processando: %s", titulo[:80])

        # 1. Extração de conteúdo (cascade)
        extraction = await extract_content(
            url=url,
            resumo=payload.get("resumo", ""),
            og_image=payload.get("og_image"),
        )
        conteudo = extraction.get("conteudo", "")
        if not conteudo or len(conteudo) < 50:
            logger.warning("Conteúdo insuficiente para %s (método=%s)", url[:60], extraction.get("metodo"))
            conteudo = payload.get("resumo", titulo)

        # 2. Contextualização RAG (artigos similares)
        similar_articles = []
        if self.memory:
            try:
                # Usar embedding do título para busca semântica
                similar_articles = await self.memory.search_articles(
                    embedding=await self._get_embedding(titulo),
                    limit=3,
                    min_similarity=0.4,
                )
            except Exception:
                logger.debug("RAG contextualização indisponível", exc_info=True)

        # 3. Redação via LLM PREMIUM
        article_data = await write_article(
            router=self.router,
            titulo_original=titulo,
            conteudo=conteudo,
            url_fonte=url,
            fonte_nome=payload.get("fonte_nome", "fonte"),
            editoria=payload.get("editoria", "geral"),
            similar_articles=similar_articles,
        )

        # 4. Otimização SEO via LLM PADRAO
        seo_data = await optimize_seo(
            router=self.router,
            titulo=article_data.get("titulo", titulo),
            resumo=article_data.get("resumo", ""),
            corpo=article_data.get("corpo", ""),
            editoria=payload.get("editoria", "geral"),
        )

        # 5. Publicação no WordPress (status=publish SEMPRE - Regra #1)
        final_titulo = seo_data.get("titulo_seo") or article_data.get("titulo", titulo)
        result = await publish_to_wordpress(
            wp_client=self.wp,
            titulo=final_titulo,
            corpo=article_data.get("corpo", ""),
            resumo=article_data.get("resumo", ""),
            editoria=payload.get("editoria", "geral"),
            categoria_wp_id=payload.get("categoria_wp_id", 1),
            slug=seo_data.get("slug"),
            tags=article_data.get("tags", []) + seo_data.get("keywords", []),
            meta_description=seo_data.get("meta_description"),
        )

        wp_post_id = result.get("id")
        if not wp_post_id:
            logger.error("Publicação falhou para: %s", titulo[:60])
            return None

        # 6. Registrar no PostgreSQL
        await self._register_article(payload, wp_post_id, article_data, seo_data)

        # 7. Retorno para evento article-published
        return {
            "wp_post_id": wp_post_id,
            "titulo": final_titulo,
            "resumo": article_data.get("resumo", ""),
            "url_fonte": url,
            "url_hash": url_hash,
            "editoria": payload.get("editoria", "geral"),
            "categoria_wp_id": payload.get("categoria_wp_id", 1),
            "relevancia_score": payload.get("relevancia_score", 0.0),
            "urgencia": payload.get("urgencia", "NORMAL"),
            "fonte_id": payload.get("fonte_id", 0),
            "fonte_nome": payload.get("fonte_nome", ""),
            "conteudo_html": extraction.get("conteudo_html"),
            "og_image": extraction.get("og_image"),
            "publicado_em": datetime.now(timezone.utc).isoformat(),
        }

    async def _register_article(self, payload, wp_post_id, article_data, seo_data):
        """Registra artigo publicado no PostgreSQL."""
        if self.pg_pool is None:
            return
        try:
            async with self.pg_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO artigos (wp_post_id, url_hash, titulo, resumo, conteudo, url_fonte,
                        editoria, categoria_wp_id, fonte_id, fonte_nome, relevancia_score,
                        urgencia, status, publicado_em)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, 'publicado', NOW())
                    ON CONFLICT (url_hash) DO NOTHING
                    """,
                    wp_post_id,
                    payload.get("url_hash", ""),
                    article_data.get("titulo", payload.get("titulo", "")),
                    article_data.get("resumo", ""),
                    article_data.get("corpo", ""),
                    payload.get("url", ""),
                    payload.get("editoria", "geral"),
                    payload.get("categoria_wp_id", 1),
                    payload.get("fonte_id", 0),
                    payload.get("fonte_nome", ""),
                    payload.get("relevancia_score", 0.0),
                    payload.get("urgencia", "NORMAL"),
                )
        except Exception:
            logger.warning("Falha ao registrar artigo no PostgreSQL", exc_info=True)

    async def _get_embedding(self, text: str) -> list[float]:
        """Gera embedding para busca semântica. Fallback: vetor zero."""
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
            embedding = model.encode([text[:512]], normalize_embeddings=True)[0]
            return embedding.tolist()
        except Exception:
            return [0.0] * 384  # MiniLM dimension
