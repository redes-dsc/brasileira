"""Redação de artigo com Smart Router."""

from __future__ import annotations

from shared.schemas import LLMRequest


async def redigir_artigo(router, titulo: str, conteudo: str, categoria: str) -> dict:
    """Gera estrutura de artigo em JSON via tier PREMIUM."""

    request = LLMRequest(
        task_type="redacao_artigo",
        messages=[
            {"role": "system", "content": "Você é um repórter jornalístico brasileiro."},
            {
                "role": "user",
                "content": (
                    "Escreva um artigo objetivo em pt-BR em JSON com campos "
                    "titulo, subtitulo, corpo, resumo, categoria. "
                    f"Categoria alvo: {categoria}.\n\nBase:\nTítulo: {titulo}\nConteúdo: {conteudo[:6000]}"
                ),
            },
        ],
        temperature=0.3,
        max_tokens=1200,
        response_format={"type": "json_object"},
    )
    response = await router.route_request(request)
    return {
        "raw": response.content,
        "modelo": f"{response.provider}/{response.model}",
        "tokens_in": response.tokens_in,
        "tokens_out": response.tokens_out,
        "tier_used": response.tier_used.value,
    }
