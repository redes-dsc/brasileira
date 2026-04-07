"""Detector de macrotemas — clusters temáticos transversais.

Identifica quando um mesmo assunto (tag) aparece em múltiplas editorias,
sinalizando um macrotema que merece destaque especial na homepage.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)


def detect_macrotemas(
    posts: list[dict[str, Any]],
    min_posts: int = 5,
    min_categories: int = 2,
) -> list[dict[str, Any]]:
    """Detecta clusters temáticos transversais por tags compartilhadas.

    Algoritmo:
      1. Indexa posts por tag_id
      2. Para cada tag com >= min_posts: verifica diversidade de categorias
      3. Se categorias >= min_categories → candidato a macrotema
      4. Pontua e ordena por relevância

    Retorna lista de macrotemas detectados.
    """

    if not posts:
        return []

    # Índice: tag_id → lista de posts
    tag_index: dict[int, list[dict[str, Any]]] = defaultdict(list)

    # Mapa de nomes de tags: tag_id → tag_name
    tag_names: dict[int, str] = {}

    for post in posts:
        tags = post.get("tags", [])
        if not isinstance(tags, list):
            continue
        for tag in tags:
            if isinstance(tag, dict):
                tag_id = tag.get("id", 0)
                tag_name = tag.get("name", "")
            elif isinstance(tag, int):
                tag_id = tag
                tag_name = ""
            else:
                continue

            if tag_id <= 0:
                continue

            tag_index[tag_id].append(post)
            if tag_name and tag_id not in tag_names:
                tag_names[tag_id] = tag_name

    # Detectar macrotemas
    macrotemas: list[dict[str, Any]] = []

    for tag_id, tag_posts in tag_index.items():
        if len(tag_posts) < min_posts:
            continue

        # Categorias únicas desses posts
        unique_categories: set[int] = set()
        for p in tag_posts:
            for cat_id in p.get("categories", []):
                if isinstance(cat_id, int):
                    unique_categories.add(cat_id)

        if len(unique_categories) < min_categories:
            continue

        # Calcular score do macrotema
        post_count = len(tag_posts)
        category_breadth = len(unique_categories)
        avg_score = sum(p.get("score_final", 0.0) for p in tag_posts) / max(1, post_count)
        macrotema_score = round(post_count * category_breadth * (avg_score / 50.0), 2)

        # IDs dos posts (ordenados por score)
        sorted_posts = sorted(tag_posts, key=lambda p: p.get("score_final", 0), reverse=True)
        post_ids = [p["id"] for p in sorted_posts]

        macrotemas.append({
            "tag_id": tag_id,
            "tag_name": tag_names.get(tag_id, f"tag_{tag_id}"),
            "posts": post_ids,
            "categories": list(unique_categories),
            "post_count": post_count,
            "category_breadth": category_breadth,
            "avg_score": round(avg_score, 2),
            "score": macrotema_score,
        })

    # Ordenar por score decrescente
    macrotemas.sort(key=lambda m: m["score"], reverse=True)

    logger.info(
        "Macrotemas: %d detectados (top: %s — %.1f pts)",
        len(macrotemas),
        macrotemas[0]["tag_name"] if macrotemas else "nenhum",
        macrotemas[0]["score"] if macrotemas else 0,
    )
    return macrotemas
