"""Reescrita editorial para cenário com 1 matéria própria."""

from __future__ import annotations

import json

from shared.schemas import LLMRequest


class Rewriter:
    """Executa reescrita com task PREMIUM de consolidação."""

    async def reescrever(self, router, tema: str, materia: dict, concorrentes: list[dict]) -> dict:
        """Retorna conteúdo JSON reescrito."""

        request = LLMRequest(
            task_type="consolidacao_sintese",
            messages=[
                {"role": "system", "content": "Você é editor jornalístico brasileiro. Reescreva sem inventar fatos."},
                {
                    "role": "user",
                    "content": (
                        "Tema: "
                        f"{tema}\n\n"
                        f"Matéria própria: {json.dumps(materia, ensure_ascii=False)}\n\n"
                        f"Referências concorrentes: {json.dumps(concorrentes, ensure_ascii=False)}\n\n"
                        "Retorne JSON com: titulo, resumo, corpo."
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=1400,
            response_format={"type": "json_object"},
        )
        response = await router.route_request(request)
        return json.loads(response.content)
