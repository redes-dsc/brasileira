"""Geração de queries de imagem via tier PREMIUM."""

from __future__ import annotations

import json
import logging

from shared.schemas import LLMRequest

logger = logging.getLogger(__name__)


async def generate_image_query(router, titulo: str, editoria: str) -> str:
    """Gera query otimizada para busca de imagem via LLM PREMIUM.

    Retorna uma string de busca. Em caso de falha, retorna o título original.
    """
    request = LLMRequest(
        task_type="imagem_query",
        messages=[
            {"role": "system", "content": "Você gera queries precisas para buscar imagens jornalísticas. Retorne APENAS a query, sem explicação."},
            {
                "role": "user",
                "content": (
                    f"Gere uma query de busca de imagem em inglês para o artigo:\n"
                    f"Título: {titulo}\nEditoria: {editoria}\n"
                    f"Retorne apenas a query de busca, sem aspas nem explicação."
                ),
            },
        ],
        temperature=0.4,
        max_tokens=100,
    )
    try:
        response = await router.route_request(request)
        query = response.content.strip().strip('"').strip("'")
        if query:
            return query
    except Exception:
        logger.debug("generate_image_query falhou, usando título", exc_info=True)
    return titulo


class QueryGenerator:
    """Gera queries para os 4 tiers de busca/geração (compatibilidade)."""

    def __init__(self, router):
        self.router = router

    async def generate(self, title: str, content: str, editoria: str, source_url: str) -> dict:
        request = LLMRequest(
            task_type="imagem_query",
            messages=[
                {"role": "system", "content": "Você gera queries precisas para buscar imagens jornalísticas."},
                {
                    "role": "user",
                    "content": (
                        "Retorne JSON com arrays tier1, tier2, tier3 e fallback_pt. "
                        f"Título: {title}\nEditoria: {editoria}\nFonte: {source_url}\nResumo: {content[:800]}"
                    ),
                },
            ],
            temperature=0.4,
            max_tokens=500,
            response_format={"type": "json_object"},
        )
        response = await self.router.route_request(request)
        try:
            data = json.loads(response.content)
            return {
                "tier1": data.get("tier1", [title]),
                "tier2": data.get("tier2", [title]),
                "tier3": data.get("tier3", [title]),
                "fallback_pt": data.get("fallback_pt", [f"{editoria} brasil notícia"]),
            }
        except Exception:
            return {
                "tier1": [title],
                "tier2": [title],
                "tier3": [f"{title} editorial illustration"],
                "fallback_pt": [f"{editoria} brasil notícia"],
            }
