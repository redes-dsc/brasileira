"""Redação de artigo jornalístico via LLM PREMIUM."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from shared.schemas import LLMRequest

logger = logging.getLogger(__name__)


async def write_article(
    router,
    titulo_original: str,
    conteudo: str,
    url_fonte: str,
    fonte_nome: str,
    editoria: str,
    similar_articles: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Redige artigo jornalístico completo via LLM PREMIUM."""

    # Contexto RAG (artigos similares)
    rag_context = ""
    if similar_articles:
        rag_context = "\n\nARTIGOS ANTERIORES RELACIONADOS (evite repetir, acrescente profundidade):\n"
        for art in similar_articles[:3]:
            rag_context += f"- {art.get('titulo', 'N/A')} ({art.get('editoria', 'N/A')})\n"

    prompt = f"""Você é um jornalista profissional do portal brasileira.news.
Reescreva a notícia abaixo em português brasileiro, seguindo o estilo jornalístico:

REGRAS:
- Pirâmide invertida (informação mais importante primeiro)
- Mínimo 300 palavras no corpo
- HTML com parágrafos <p>, subtítulos <h2> quando apropriado
- OBRIGATÓRIO: No 1º ou 2º parágrafo, cite a fonte original com link HTML: <a href="{url_fonte}">{fonte_nome}</a>
- Nunca invente dados, nomes, números ou citações
- Tom formal, voz ativa, frases diretas
{rag_context}
FONTE ORIGINAL: {url_fonte}
TÍTULO ORIGINAL: {titulo_original}
CONTEÚDO:
{conteudo[:3000]}

Responda APENAS em JSON:
{{"titulo": "...", "subtitulo": "...", "corpo": "<p>...</p>", "resumo": "...(max 160 chars)", "tags": ["tag1", "tag2"]}}"""

    for attempt in range(3):
        request = LLMRequest(
            task_type="redacao_artigo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=3000,
            timeout=60,
        )
        response = await router.route_request(request)

        try:
            # Tenta extrair JSON da resposta
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0]
            data = json.loads(content)
            if "titulo" in data and "corpo" in data:
                return data
        except (json.JSONDecodeError, KeyError):
            if attempt < 2:
                logger.warning("Resposta LLM não é JSON válido (tentativa %d), retentando", attempt + 1)
                continue

    # Fallback: usar conteúdo extraído diretamente
    logger.warning("Todas as tentativas de redação falharam, usando conteúdo extraído")
    return {
        "titulo": titulo_original,
        "subtitulo": "",
        "corpo": f"<p>{conteudo[:2000]}</p>",
        "resumo": conteudo[:155],
        "tags": [],
    }
