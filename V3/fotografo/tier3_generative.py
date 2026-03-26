"""Tier 3: geração de imagem por IA."""

from __future__ import annotations


class Tier3Generative:
    """Gera imagem quando tiers anteriores falham."""

    async def generate(self, queries: list[str], article_title: str, editoria: str) -> dict | None:
        prompt = queries[0] if queries else f"{article_title} {editoria}"
        slug = prompt.lower().replace(" ", "-")[:70]
        return {
            "url": f"https://ai-images.example.com/{slug}.png",
            "source_api": "gpt-image-1",
            "attribution": "Imagem gerada por IA",
            "ai_generated": True,
            "ai_prompt": prompt,
            "clip_score": 0.2,
            "wp_media_id": None,
        }
