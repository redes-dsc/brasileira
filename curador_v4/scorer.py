"""Scoring objetivo + editorial para candidatos da homepage (V4).

Usa LiteLLM diretamente via httpx, sem dependência do router V3.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from curador_v4.config import CuradorConfig

logger = logging.getLogger(__name__)

# Categorias de alta prioridade (política, economia, internacional)
_PRIORITY_CATEGORIES: set[int] = {15285, 15661, 88}


def objective_score(post: dict[str, Any]) -> float:
    """Score local 0-50 baseado em recência, categoria, imagem e título.

    Composição:
      - Recência (0-15): posts mais recentes pontuam mais
      - Categoria prioritária (0-12): política/economia/internacional
      - Imagem (0-8): bônus por ter imagem destacada
      - Título (0-8): comprimento adequado de título
      - Tags (0-7): mais tags indicam mais contexto
    """

    score = 0.0

    # --- Recência (0-15 pontos) ---
    date_str = post.get("date_gmt", "")
    if isinstance(date_str, str) and date_str:
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_hours = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600)
            # Decaimento linear: 15 pontos se acabou de sair, 0 se >6h
            score += max(0.0, 15.0 - (age_hours * 2.5))
        except (ValueError, TypeError):
            score += 2.0

    # --- Categoria prioritária (0-12 pontos) ---
    categories = post.get("categories", [])
    if any(cat_id in _PRIORITY_CATEGORIES for cat_id in categories):
        score += 12.0
    elif categories:
        score += 5.0

    # --- Imagem destacada (0-8 pontos) ---
    if post.get("featured_image"):
        score += 8.0

    # --- Qualidade do título (0-8 pontos) ---
    title = post.get("title", "")
    title_len = len(title)
    if 30 <= title_len <= 100:
        score += 8.0
    elif 15 <= title_len < 30:
        score += 5.0
    elif title_len > 100:
        score += 4.0
    else:
        score += 2.0

    # --- Tags (0-7 pontos) ---
    tags = post.get("tags", [])
    tag_count = len(tags) if isinstance(tags, list) else 0
    score += min(7.0, tag_count * 1.5)

    return round(min(50.0, score), 2)


async def editorial_score(
    config: CuradorConfig,
    posts: list[dict[str, Any]],
) -> dict[int, float]:
    """Pontuação editorial via LLM PREMIUM (LiteLLM).

    Envia candidatos para o LLM e recebe notas 0-50.
    """

    if not posts:
        return {}

    # Preparar candidatos resumidos para o LLM
    candidates = []
    for p in posts:
        # Calcular idade em horas
        age_hours = 0.0
        date_str = p.get("date_gmt", "")
        if isinstance(date_str, str) and date_str:
            try:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                age_hours = round((datetime.now(timezone.utc) - dt).total_seconds() / 3600, 1)
            except (ValueError, TypeError):
                pass

        excerpt = p.get("excerpt", "")
        # Limpar HTML básico do excerpt
        excerpt_clean = excerpt.replace("<p>", "").replace("</p>", "").strip()[:200]

        candidates.append({
            "post_id": p["id"],
            "title": p.get("title", ""),
            "excerpt": excerpt_clean,
            "categories": p.get("categories", []),
            "age_hours": age_hours,
        })

    messages = [
        {
            "role": "system",
            "content": (
                "Você é o editor-chefe da homepage do brasileira.news, o principal portal "
                "jornalístico automatizado do Brasil. Avalie cada candidato com nota de 0 a 50, "
                "considerando: impacto nacional, utilidade pública, relevância imediata, "
                "diversidade editorial e potencial de engajamento. "
                "Posts urgentes e de alto impacto devem receber notas > 40. "
                "Retorne APENAS JSON válido."
            ),
        },
        {
            "role": "user",
            "content": (
                'Retorne JSON no formato {"scores": [{"post_id": int, "score": float}]}.\n\n'
                f"Candidatos:\n{json.dumps(candidates, ensure_ascii=False)}"
            ),
        },
    ]

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{config.litellm_base_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.litellm_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config.llm_model,
                    "messages": messages,
                    "temperature": 0.1,
                    "max_tokens": 2000,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.error("Falha na chamada LLM editorial: %s", exc)
        return {}

    # Extrair conteúdo da resposta
    try:
        content = data["choices"][0]["message"]["content"]
        payload = json.loads(content)
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        logger.error("Resposta LLM inválida: %s", exc)
        return {}

    # Parsear scores
    out: dict[int, float] = {}
    for item in payload.get("scores", []):
        try:
            post_id = int(item["post_id"])
            raw_score = float(item["score"])
            out[post_id] = round(min(50.0, max(0.0, raw_score)), 2)
        except (KeyError, ValueError, TypeError):
            continue

    logger.info("Editorial score: %d posts pontuados via LLM", len(out))
    return out


async def score_posts(
    config: CuradorConfig,
    posts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Combina score objetivo + editorial. Retorna posts com scores adicionados."""

    if not posts:
        return []

    # 1. Calcular scores objetivos para todos
    for post in posts:
        post["score_objective"] = objective_score(post)

    # 2. Selecionar top 50 por score objetivo para avaliação editorial
    sorted_by_obj = sorted(posts, key=lambda p: p["score_objective"], reverse=True)
    top_candidates = sorted_by_obj[:50]

    # 3. Score editorial via LLM
    llm_scores = await editorial_score(config, top_candidates)

    # 4. Combinar scores
    for post in posts:
        ed_score = llm_scores.get(post["id"], 0.0)
        post["score_editorial"] = ed_score
        post["score_final"] = round(post["score_objective"] + ed_score, 2)

    # 5. Ordenar por score final
    posts.sort(key=lambda p: p["score_final"], reverse=True)

    logger.info(
        "Scoring: %d posts pontuados (top: %s — %.1f pts)",
        len(posts),
        posts[0].get("title", "?")[:50] if posts else "N/A",
        posts[0].get("score_final", 0) if posts else 0,
    )
    return posts
