"""Reescrita editorial para cenário com 1 matéria própria."""

from __future__ import annotations

import json
import logging

from shared.schemas import LLMRequest

logger = logging.getLogger(__name__)


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
        try:
            return json.loads(response.content)
        except json.JSONDecodeError as e:
            logger.error("rewriter: LLM retornou JSON inválido: %s — resposta: %.300s", e, response.content)
            raise ValueError(f"LLM retornou JSON inválido na reescrita: {e}") from e
