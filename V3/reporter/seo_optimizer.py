"""Otimização SEO via LLM PADRAO."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from shared.schemas import LLMRequest

logger = logging.getLogger(__name__)


async def optimize_seo(
    router,
    titulo: str,
    resumo: str,
    corpo: str,
    editoria: str,
) -> dict[str, Any]:
    """Otimiza título, meta description, slug e keywords para SEO."""
    prompt = f"""Otimize o SEO desta notícia:

Título: {titulo}
Resumo: {resumo}
Editoria: {editoria}
Primeiros parágrafos: {corpo[:500]}

Responda em JSON:
{{"titulo_seo": "...(max 65 chars)", "meta_description": "...(max 155 chars)", "slug": "...(kebab-case)", "keywords": ["kw1", "kw2", "kw3"]}}"""

    try:
        request = LLMRequest(
            task_type="seo_otimizacao",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.2,
        )
        response = await router.route_request(request)
        content = response.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]
        data = json.loads(content)
        # Validações
        if len(data.get("titulo_seo", "")) > 70:
            data["titulo_seo"] = data["titulo_seo"][:67] + "..."
        if len(data.get("meta_description", "")) > 160:
            data["meta_description"] = data["meta_description"][:157] + "..."
        return data
    except Exception:
        logger.warning("SEO optimization falhou, usando fallback", exc_info=True)
        # Fallback determinístico
        slug = re.sub(r"[^a-z0-9]+", "-", titulo.lower()[:60]).strip("-")
        return {
            "titulo_seo": titulo[:65],
            "meta_description": resumo[:155],
            "slug": slug,
            "keywords": [],
        }
