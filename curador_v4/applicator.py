"""Aplicador de layout na API REST do brasileira.news."""

from __future__ import annotations

import logging
from typing import Any

from curador_v4.config import CuradorConfig

logger = logging.getLogger(__name__)

# Endpoint base da API customizada do tema brasileira
_API_BASE = "/wp-json/brasileira/v1"


async def apply_layout(
    wp_client: Any,
    config: CuradorConfig,
    page_id: int,
    diff: dict[str, Any],
) -> bool:
    """Aplica layout via REST API do brasileira.news.

    Suporta PUT (substituição completa) e PATCH (incremental).
    """

    if diff["method"] == "PUT":
        try:
            await wp_client.request(
                "PUT",
                f"{_API_BASE}/layout/{page_id}",
                json=diff["full_layout"],
            )
            logger.info("Layout aplicado via PUT (substituição completa)")
            return True
        except Exception as exc:
            logger.error("Falha ao aplicar layout via PUT: %s", exc)
            return False

    # Modo PATCH: operações incrementais
    success = True

    # Adicionar novos blocos
    for block in diff.get("added", []):
        try:
            await wp_client.post(
                f"{_API_BASE}/layout/{page_id}/blocks",
                json=block,
            )
        except Exception as exc:
            logger.error("Falha ao adicionar bloco %s: %s", block.get("id", "?"), exc)
            success = False

    # Remover blocos
    for block_id in diff.get("removed", []):
        try:
            await wp_client.delete(
                f"{_API_BASE}/layout/{page_id}/blocks/{block_id}",
            )
        except Exception as exc:
            logger.error("Falha ao remover bloco %s: %s", block_id, exc)
            success = False

    # Atualizar blocos existentes
    for block in diff.get("updated", []):
        try:
            await wp_client.patch(
                f"{_API_BASE}/layout/{page_id}/blocks/{block['id']}",
                json=block,
            )
        except Exception as exc:
            logger.error("Falha ao atualizar bloco %s: %s", block.get("id", "?"), exc)
            success = False

    changes = diff.get("changes", {})
    logger.info(
        "Layout aplicado via PATCH — +%d -%d ~%d blocos (sucesso: %s)",
        changes.get("added", 0),
        changes.get("removed", 0),
        changes.get("updated", 0),
        success,
    )
    return success


async def manage_macrotemas(
    wp_client: Any,
    config: CuradorConfig,
    current_macrotemas: list[dict[str, Any]],
    detected_macrotemas: list[dict[str, Any]],
) -> None:
    """Cria/arquiva páginas de macrotemas conforme detecção.

    Cria novos macrotemas detectados e arquiva os que decaíram.
    """

    current_tags: set[int] = set()
    for mt in current_macrotemas:
        tag_id = mt.get("tag_id")
        if isinstance(tag_id, int):
            current_tags.add(tag_id)

    detected_tags: set[int] = set()
    for mt in detected_macrotemas:
        tag_id = mt.get("tag_id")
        if isinstance(tag_id, int):
            detected_tags.add(tag_id)

    # Criar macrotemas novos
    for mt in detected_macrotemas:
        tag_id = mt.get("tag_id")
        if tag_id not in current_tags:
            try:
                await wp_client.post(
                    f"{_API_BASE}/macrotema",
                    json={
                        "tag_id": tag_id,
                        "label": mt.get("tag_name", f"Macrotema {tag_id}"),
                        "posts": mt.get("posts", [])[:6],
                    },
                )
                logger.info("Macrotema criado: %s (tag %d)", mt.get("tag_name"), tag_id)
            except Exception as exc:
                logger.warning("Falha ao criar macrotema tag %d: %s", tag_id, exc)

    # Arquivar macrotemas que decaíram
    decayed = current_tags - detected_tags
    for tag_id in decayed:
        try:
            await wp_client.delete(f"{_API_BASE}/macrotema/{tag_id}")
            logger.info("Macrotema arquivado: tag %d", tag_id)
        except Exception as exc:
            logger.warning("Falha ao arquivar macrotema tag %d: %s", tag_id, exc)
