"""Otimização SEO com tier PADRÃO."""

from __future__ import annotations

from shared.schemas import LLMRequest


async def otimizar_seo(router, titulo: str, resumo: str) -> dict:
    """Gera título SEO, meta descrição e slug."""

    request = LLMRequest(
        task_type="seo_otimizacao",
        messages=[
            {"role": "system", "content": "Você é especialista em SEO editorial."},
            {
                "role": "user",
                "content": (
                    "Retorne JSON com title_seo, meta_description e slug. "
                    f"Título: {titulo}\nResumo: {resumo}"
                ),
            },
        ],
        temperature=0.2,
        max_tokens=300,
        response_format={"type": "json_object"},
    )
    response = await router.route_request(request)
    return {"raw": response.content, "modelo": f"{response.provider}/{response.model}"}
