"""Publicação no WordPress com status publish."""

from __future__ import annotations


async def publicar_no_wordpress(wp_client, payload: dict) -> dict:
    """Publica artigo imediatamente no WP (sem draft)."""

    request_payload = {
        "title": payload["title"],
        "content": payload["content"],
        "excerpt": payload.get("excerpt", ""),
        "status": "publish",
        "categories": payload.get("categories", []),
        "tags": payload.get("tags", []),
        "slug": payload.get("slug"),
        "meta": payload.get("meta", {}),
    }
    return await wp_client.post("/wp-json/wp/v2/posts", json=request_payload)
