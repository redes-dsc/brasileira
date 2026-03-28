"""Consolidação analítica para cenário com 2+ matérias próprias."""

from __future__ import annotations

import json

from shared.schemas import LLMRequest


class Merger:
    """Consolida múltiplas matérias em um texto analítico único."""

    async def consolidar(self, router, tema: str, materias: list[dict], concorrentes: list[dict]) -> dict:
        """Retorna conteúdo JSON consolidado."""

        request = LLMRequest(
            task_type="consolidacao_sintese",
            messages=[
                {
                    "role": "system",
                    "content": "Você é editor analítico. Consolide perspectivas sem contradizer os dados fornecidos.",
                },
                {
                    "role": "user",
                    "content": (
                        f"Tema: {tema}\n\n"
                        f"Matérias próprias: {json.dumps(materias, ensure_ascii=False)}\n\n"
                        f"Contexto concorrentes: {json.dumps(concorrentes, ensure_ascii=False)}\n\n"
                        "Retorne JSON com: titulo, resumo, corpo, principais_pontos (lista)."
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=1800,
            response_format={"type": "json_object"},
        )
        response = await router.route_request(request)
        return json.loads(response.content)
