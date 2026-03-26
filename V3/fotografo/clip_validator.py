"""Validador de similaridade (stub determinístico para runtime sem CLIP pesado)."""

from __future__ import annotations


class CLIPValidator:
    """Valida aderência imagem-texto com score 0-1."""

    async def score(self, image_url: str, article_text: str) -> float:
        """Score aproximado por heurística lexical no URL."""

        text = article_text.lower()
        url = image_url.lower()
        tokens = [token for token in text.split() if len(token) > 4][:12]
        overlap = sum(1 for token in tokens if token in url)
        base = 0.18 if overlap > 0 else 0.11
        return min(0.9, base + overlap * 0.04)
