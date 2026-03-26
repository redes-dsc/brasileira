"""Tier 1: extração de imagem original (og:image)."""

from __future__ import annotations

import re


class Tier1Original:
    """Extrai imagem da própria fonte quando disponível."""

    async def extract(self, source_url: str, html_content: str | None) -> dict:
        if not html_content:
            return {"success": False, "candidate": None}

        match = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', html_content, re.I)
        if not match:
            return {"success": False, "candidate": None}

        candidate = {
            "url": match.group(1),
            "source_api": "source_og",
            "attribution": source_url,
            "ai_generated": False,
            "clip_score": None,
            "wp_media_id": None,
        }
        return {"success": True, "candidate": candidate}
