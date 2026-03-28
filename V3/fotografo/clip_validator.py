"""Validação de relevância imagem-texto."""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def validate_image_relevance(
    image_url: str,
    article_text: str,
    min_score: float = 0.15,
) -> tuple[bool, float]:
    """Valida se a imagem é relevante para o artigo.

    Usa heurísticas de URL + metadados. Para produção CLIP real,
    instalar transformers + PIL e descomentar a seção CLIP.
    """
    score = 0.0

    # Heurística 1: tokens do texto na URL
    text_tokens = set(article_text.lower().split()[:20])
    url_lower = image_url.lower()
    matches = sum(1 for t in text_tokens if len(t) > 4 and t in url_lower)
    score += min(matches * 0.05, 0.2)

    # Heurística 2: extensão de imagem válida
    if any(ext in url_lower for ext in (".jpg", ".jpeg", ".png", ".webp")):
        score += 0.1

    # Heurística 3: não é placeholder/genérico
    if not any(generic in url_lower for generic in ("placeholder", "default", "no-image", "noimage")):
        score += 0.1

    # Heurística 4: tem dimensões razoáveis na URL
    if any(size in url_lower for size in ("large", "1024", "1200", "2x", "full", "original")):
        score += 0.05

    # Base score para imagens de stock/originais reais
    if any(domain in url_lower for domain in ("pexels.com", "unsplash.com", "agenciabrasil")):
        score += 0.15

    is_valid = score >= min_score
    return is_valid, score
