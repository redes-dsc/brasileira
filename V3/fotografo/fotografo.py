"""Pipeline Fotógrafo: 4-tier fallback para featured image."""

from __future__ import annotations

import logging
from typing import Any, Optional

from .tier1_original import Tier1Extractor
from .tier2_stocks import Tier2StockSearch
from .tier3_generative import Tier3Generator
from .tier4_placeholder import Tier4Placeholder
from .query_generator import generate_image_query

logger = logging.getLogger(__name__)


class FotografoAgent:
    """Pipeline de 4 tiers com fallback garantido para imagem editorial."""

    def __init__(self, router=None):
        self.router = router
        self.tier1 = Tier1Extractor()
        self.tier2 = Tier2StockSearch()
        self.tier3 = Tier3Generator()
        self.tier4 = Tier4Placeholder()

    async def processar(self, event: dict[str, Any]) -> dict[str, Any]:
        """Processa evento article-published e retorna imagem selecionada."""
        titulo = event.get("titulo", "")
        editoria = event.get("editoria", "geral")
        html_content = event.get("conteudo_html")
        url_fonte = event.get("url_fonte", "")
        og_image = event.get("og_image")
        wp_post_id = event.get("wp_post_id")

        logger.info("Fotógrafo processando: wp_post_id=%s titulo=%s", wp_post_id, titulo[:60])

        # Tier 1: Extração original
        result = await self.tier1.extract(html_content, url_fonte, og_image)
        if result.get("success"):
            logger.info("Tier 1 sucesso (%s) para wp_post_id=%s", result.get("source"), wp_post_id)
            return self._build_result(result, wp_post_id, editoria)

        # Gerar query para busca
        search_query = titulo
        if self.router:
            try:
                search_query = await generate_image_query(self.router, titulo, editoria)
            except Exception:
                logger.debug("Query generation falhou, usando título")

        # Tier 2: Stock photos
        result = await self.tier2.search(search_query, editoria)
        if result.get("success"):
            logger.info("Tier 2 sucesso (%s) para wp_post_id=%s", result.get("source"), wp_post_id)
            return self._build_result(result, wp_post_id, editoria)

        # Tier 3: AI generativa
        result = await self.tier3.generate(search_query, editoria)
        if result.get("success"):
            logger.info("Tier 3 sucesso (%s) para wp_post_id=%s", result.get("source"), wp_post_id)
            return self._build_result(result, wp_post_id, editoria)

        # Tier 4: Placeholder (GARANTIA — nunca falha, Regra #3)
        result = self.tier4.get_placeholder(editoria)
        logger.info("Tier 4 placeholder para wp_post_id=%s editoria=%s", wp_post_id, editoria)
        return self._build_result(result, wp_post_id, editoria)

    def _build_result(self, tier_result: dict, wp_post_id: Any, editoria: str) -> dict[str, Any]:
        return {
            "wp_post_id": wp_post_id,
            "image_url": tier_result.get("url", ""),
            "source": tier_result.get("source", "unknown"),
            "tier": tier_result.get("tier", 0),
            "ai_generated": tier_result.get("ai_generated", False),
            "ai_label": tier_result.get("ai_label"),
            "attribution": tier_result.get("attribution"),
            "alt": tier_result.get("alt", f"Imagem: {editoria}"),
            "editoria": editoria,
        }

    async def close(self):
        await self.tier2.close()
        await self.tier3.close()
