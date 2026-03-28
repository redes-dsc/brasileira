"""Publicação no WordPress com status=publish (Regra #1)."""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


async def publish_to_wordpress(
    wp_client,
    titulo: str,
    corpo: str,
    resumo: str,
    editoria: str,
    categoria_wp_id: int,
    slug: Optional[str] = None,
    tags: Optional[list[str]] = None,
    meta_description: Optional[str] = None,
) -> dict[str, Any]:
    """Publica artigo no WordPress. Sempre status=publish (nunca draft)."""

    post_data: dict[str, Any] = {
        "title": titulo,
        "content": corpo,
        "excerpt": resumo[:300],
        "status": "publish",
        "categories": [categoria_wp_id],
    }
    if slug:
        post_data["slug"] = slug
    if tags:
        # Busca ou cria tags no WP
        tag_ids = await _resolve_tags(wp_client, tags)
        if tag_ids:
            post_data["tags"] = tag_ids

    result = await wp_client.post("/wp-json/wp/v2/posts", json=post_data)
    wp_post_id = result.get("id")

    if wp_post_id:
        logger.info("Artigo publicado: wp_post_id=%d titulo=%s", wp_post_id, titulo[:60])
    else:
        logger.error("WordPress não retornou ID para artigo: %s", titulo[:60])

    return result


async def _resolve_tags(wp_client, tags: list[str]) -> list[int]:
    """Busca IDs de tags existentes ou cria novas."""
    tag_ids = []
    for tag_name in tags[:5]:  # Max 5 tags
        try:
            # Busca tag existente
            existing = await wp_client.get("/wp-json/wp/v2/tags", params={"search": tag_name, "per_page": 1})
            if isinstance(existing, list) and existing:
                tag_ids.append(existing[0]["id"])
            else:
                # Cria nova tag
                new_tag = await wp_client.post("/wp-json/wp/v2/tags", json={"name": tag_name})
                if isinstance(new_tag, dict) and "id" in new_tag:
                    tag_ids.append(new_tag["id"])
        except Exception:
            logger.debug("Falha ao resolver tag '%s'", tag_name)
    return tag_ids
