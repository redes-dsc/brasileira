"""Geração de briefing para pauta especial."""

from __future__ import annotations

import json
import logging

from shared.schemas import LLMRequest

from .schemas import TrendSignal

logger = logging.getLogger(__name__)


class BriefingGenerator:
    """Gera briefing via SmartLLMRouter com task_type premium."""

    def __init__(self, router=None):
        self.router = router

    async def generate(self, editoria: str, signals: list[TrendSignal]) -> str:
        """Retorna briefing textual consolidado."""

        payload = {
            "editoria": editoria,
            "sinais": [
                {"titulo": s.titulo, "resumo": s.resumo, "fonte": s.fonte, "score": s.score}
                for s in signals[:8]
            ],
        }

        if self.router is None:
            return f"Pauta especial de {editoria}: explorar ângulos inéditos com base em {len(signals)} sinais."

        request = LLMRequest(
            task_type="pauta_especial",
            messages=[
                {"role": "system", "content": "Você é editor de pauta e gera briefings objetivos em português."},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.2,
            max_tokens=700,
        )

        try:
            response = await self.router.route_request(request)
            return response.content.strip()
        except Exception:
            logger.exception("Falha no SmartLLMRouter para pauta_especial")
            return f"Pauta especial de {editoria}: aprofundar contexto, impactos e próximos desdobramentos."
