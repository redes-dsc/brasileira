"""Tier 4: placeholder temático (garantia de imagem)."""

from __future__ import annotations


class Tier4Placeholder:
    """Retorna placeholder por editoria, sem falhar."""

    PLACEHOLDERS = {
        "politica": (7001, "https://brasileira.news/placeholders/politica.jpg"),
        "economia": (7002, "https://brasileira.news/placeholders/economia.jpg"),
        "esportes": (7003, "https://brasileira.news/placeholders/esportes.jpg"),
        "default": (7999, "https://brasileira.news/placeholders/default.jpg"),
    }

    def get_placeholder(self, editoria: str) -> dict:
        key = (editoria or "").lower()
        media_id, url = self.PLACEHOLDERS.get(key, self.PLACEHOLDERS["default"])
        return {
            "url": url,
            "source_api": "placeholder",
            "attribution": "Placeholder temática brasileira.news",
            "ai_generated": False,
            "clip_score": 1.0,
            "wp_media_id": media_id,
        }
