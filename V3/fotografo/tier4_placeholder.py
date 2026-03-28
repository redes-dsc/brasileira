"""Tier 4: Placeholder temático por editoria (garantia — sempre retorna imagem)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Placeholders por editoria (devem ser URLs de imagens reais no WP)
PLACEHOLDERS: dict[str, dict[str, Any]] = {
    "politica": {"url": "/wp-content/uploads/placeholders/politica.jpg", "alt": "Imagem ilustrativa: Política"},
    "economia": {"url": "/wp-content/uploads/placeholders/economia.jpg", "alt": "Imagem ilustrativa: Economia"},
    "esportes": {"url": "/wp-content/uploads/placeholders/esportes.jpg", "alt": "Imagem ilustrativa: Esportes"},
    "tecnologia": {"url": "/wp-content/uploads/placeholders/tecnologia.jpg", "alt": "Imagem ilustrativa: Tecnologia"},
    "saude": {"url": "/wp-content/uploads/placeholders/saude.jpg", "alt": "Imagem ilustrativa: Saúde"},
    "educacao": {"url": "/wp-content/uploads/placeholders/educacao.jpg", "alt": "Imagem ilustrativa: Educação"},
    "ciencia": {"url": "/wp-content/uploads/placeholders/ciencia.jpg", "alt": "Imagem ilustrativa: Ciência"},
    "cultura": {"url": "/wp-content/uploads/placeholders/cultura.jpg", "alt": "Imagem ilustrativa: Cultura"},
    "mundo": {"url": "/wp-content/uploads/placeholders/mundo.jpg", "alt": "Imagem ilustrativa: Internacional"},
    "meio_ambiente": {"url": "/wp-content/uploads/placeholders/meio_ambiente.jpg", "alt": "Imagem ilustrativa: Meio Ambiente"},
    "seguranca": {"url": "/wp-content/uploads/placeholders/seguranca.jpg", "alt": "Imagem ilustrativa: Segurança"},
    "sociedade": {"url": "/wp-content/uploads/placeholders/sociedade.jpg", "alt": "Imagem ilustrativa: Sociedade"},
    "brasil": {"url": "/wp-content/uploads/placeholders/brasil.jpg", "alt": "Imagem ilustrativa: Brasil"},
    "regionais": {"url": "/wp-content/uploads/placeholders/regionais.jpg", "alt": "Imagem ilustrativa: Regionais"},
    "opiniao": {"url": "/wp-content/uploads/placeholders/opiniao.jpg", "alt": "Imagem ilustrativa: Opinião"},
    "ultimas_noticias": {"url": "/wp-content/uploads/placeholders/ultimas.jpg", "alt": "Imagem ilustrativa: Últimas Notícias"},
}

DEFAULT_PLACEHOLDER = {"url": "/wp-content/uploads/placeholders/default.jpg", "alt": "Imagem ilustrativa: brasileira.news"}


class Tier4Placeholder:
    """Retorna placeholder temático. SEMPRE sucede (Regra #3)."""

    def get_placeholder(self, editoria: str) -> dict[str, Any]:
        """Retorna placeholder para a editoria. Garantia de 100% de sucesso."""
        placeholder = PLACEHOLDERS.get(editoria, DEFAULT_PLACEHOLDER)
        return {
            "success": True,
            "url": placeholder["url"],
            "alt": placeholder["alt"],
            "source": "placeholder",
            "tier": 4,
        }
