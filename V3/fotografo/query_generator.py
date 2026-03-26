"""Geração de queries de imagem via tier PREMIUM."""

from __future__ import annotations

import json

from shared.schemas import LLMRequest


class QueryGenerator:
    """Gera queries para os 4 tiers de busca/geração."""

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
