"""Scanner de artigos recentes via WordPress REST API."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _extract_featured_image(post: dict[str, Any]) -> str:
    """Extrai URL da imagem destacada do post embeddado."""

    embedded = post.get("_embedded", {})
    media_list = embedded.get("wp:featuredmedia", [])
    if media_list and isinstance(media_list, list):
        first = media_list[0]
        if isinstance(first, dict):
            return first.get("source_url", "")
    return ""


def _extract_author_name(post: dict[str, Any]) -> str:
    """Extrai nome do autor do post embeddado."""

    embedded = post.get("_embedded", {})
    authors = embedded.get("author", [])
    if authors and isinstance(authors, list):
        first = authors[0]
        if isinstance(first, dict):
            return first.get("name", "")
    return ""


def _extract_tags(post: dict[str, Any]) -> list[dict[str, Any]]:
    """Extrai tags do post embeddado (wp:term)."""

    embedded = post.get("_embedded", {})
    terms_groups = embedded.get("wp:term", [])
    tags: list[dict[str, Any]] = []
    for group in terms_groups:
        if not isinstance(group, list):
            continue
        for term in group:
            if isinstance(term, dict) and term.get("taxonomy") == "post_tag":
                tags.append({"id": term.get("id", 0), "name": term.get("name", "")})
    return tags


def _parse_post(post: dict[str, Any]) -> dict[str, Any]:
    """Converte um post da WP REST API para formato interno."""

    title_obj = post.get("title", {})
    excerpt_obj = post.get("excerpt", {})

    return {
        "id": int(post.get("id", 0)),
        "title": title_obj.get("rendered", "") if isinstance(title_obj, dict) else str(title_obj),
        "excerpt": excerpt_obj.get("rendered", "") if isinstance(excerpt_obj, dict) else str(excerpt_obj),
        "categories": post.get("categories", []),
        "tags_raw": post.get("tags", []),
        "tags": _extract_tags(post),
        "date_gmt": post.get("date_gmt", ""),
        "featured_image": _extract_featured_image(post),
        "author": _extract_author_name(post),
        "link": post.get("link", ""),
        "meta": post.get("meta", {}),
    }


async def scan_recent_posts(
    wp_client: Any,
    hours_back: int = 4,
    per_page: int = 100,
) -> list[dict[str, Any]]:
    """Busca posts publicados nas últimas N horas via WP REST API.

    Pagina automaticamente até esgotar resultados.
    """

    after_dt = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    after_iso = after_dt.strftime("%Y-%m-%dT%H:%M:%S")

    all_posts: list[dict[str, Any]] = []
    page = 1
    max_pages = 10  # Limite de segurança contra loops infinitos

    while page <= max_pages:
        try:
            params = {
                "after": after_iso,
                "per_page": per_page,
                "page": page,
                "orderby": "date",
                "order": "desc",
                "status": "publish",
                "_embed": "1",
            }
            response = await wp_client.get("/wp-json/wp/v2/posts", params=params)
        except Exception as exc:
            logger.warning("Erro ao buscar página %d de posts: %s", page, exc)
            break

        # Resposta vazia ou não-lista indica fim dos resultados
        if not response or not isinstance(response, list):
            break

        for raw_post in response:
            parsed = _parse_post(raw_post)
            if parsed["id"] > 0:
                all_posts.append(parsed)

        # Se retornou menos que per_page, não há mais páginas
        if len(response) < per_page:
            break

        page += 1

    logger.info("Scanner: %d posts coletados nas últimas %dh", len(all_posts), hours_back)
    return all_posts
