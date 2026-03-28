"""Tier 4: Placeholder temático por editoria (garantia — sempre retorna imagem)."""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# URL real confirmada no WordPress
DEFAULT_PLACEHOLDER_URL = "https://brasileira.news/wp-content/uploads/sites/7/2026/02/imagem-brasileira.png"

# Queries para tentar buscar na media library do WP antes de usar default
CATEGORY_SEARCH_TERMS: dict[str, str] = {
    "politica": "brasília congresso",
    "economia": "economia mercado",
    "esportes": "esporte futebol",
    "tecnologia": "tecnologia digital",
    "saude": "saúde hospital",
    "educacao": "educação escola",
    "ciencia": "ciência pesquisa",
    "cultura": "cultura arte",
    "mundo": "internacional mundo",
    "meio_ambiente": "meio ambiente natureza",
    "seguranca": "segurança polícia",
    "sociedade": "sociedade comunidade",
    "brasil": "brasil",
    "regionais": "cidade regional",
    "opiniao": "opinião editorial",
    "ultimas_noticias": "urgente notícia",
}


class Tier4Placeholder:
    """Retorna placeholder temático. SEMPRE sucede (Regra #3: nenhuma notícia sem imagem)."""

    def __init__(self, wp_client=None):
        self.wp_client = wp_client

    async def search_wp_media(self, editoria: str) -> Optional[dict[str, Any]]:
        """Tenta encontrar imagem existente na media library do WordPress."""
        if not self.wp_client:
            return None
        search_term = CATEGORY_SEARCH_TERMS.get(editoria, "brasileira")
        try:
            media = await self.wp_client.get(
                "/wp-json/wp/v2/media",
                params={"search": search_term, "per_page": 1, "media_type": "image"}
            )
            if isinstance(media, list) and media:
                return {
                    "success": True,
                    "url": media[0].get("source_url", DEFAULT_PLACEHOLDER_URL),
                    "media_id": media[0]["id"],
                    "alt": media[0].get("alt_text", f"Imagem ilustrativa: {editoria}"),
                    "source": "wordpress_media",
                    "tier": 4,
                    "is_placeholder": True,
                }
        except Exception as e:
            logger.debug("WP media search falhou para '%s': %s", search_term, e)
        return None

    def get_placeholder(self, editoria: str) -> dict[str, Any]:
        """Retorna placeholder para a editoria. Garantia de 100% de sucesso.
        
        Método síncrono para compatibilidade com fotografo.py.
        Usa URL genérica confirmada como existente no WordPress.
        """
        return {
            "success": True,
            "url": DEFAULT_PLACEHOLDER_URL,
            "alt": f"Imagem ilustrativa - {editoria.replace('_', ' ').title()}",
            "source": "placeholder",
            "tier": 4,
            "is_placeholder": True,
        }
