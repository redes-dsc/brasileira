"""Tier 2: busca em bancos de imagem (mockável)."""

from __future__ import annotations


class Tier2Stocks:
    """Busca imagens candidatas em APIs de stock."""

    async def search(self, queries: list[str]) -> dict:
        for query in queries:
            if query.strip():
                slug = query.strip().lower().replace(" ", "-")[:60]
                return {
                    "success": True,
                    "candidate": {
                        "url": f"https://images.example.com/{slug}.jpg",
                        "source_api": "pexels",
                        "attribution": "Pexels",
                        "ai_generated": False,
                        "clip_score": None,
                        "wp_media_id": None,
                    },
                    "query_used": query,
                }
        return {"success": False, "candidate": None, "query_used": None}
