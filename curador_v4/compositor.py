"""Compositor dinâmico da homepage — o cérebro editorial do Curador V4.

Monta o layout completo da homepage como lista de blocos,
usando LLM PREMIUM para decisões editoriais de ordenação.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from curador_v4.config import CuradorConfig
from curador_v4.presets import BST, LayoutPreset

logger = logging.getLogger(__name__)


def _uid() -> str:
    """Gera identificador curto para blocos."""
    return uuid.uuid4().hex[:12]


def _is_very_recent(post: dict[str, Any], minutes: int = 30) -> bool:
    """Verifica se o post foi publicado nos últimos N minutos."""

    date_str = post.get("date_gmt", "")
    if not isinstance(date_str, str) or not date_str:
        return False
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - dt
        return age <= timedelta(minutes=minutes)
    except (ValueError, TypeError):
        return False


def _group_by_editoria(
    posts: list[dict[str, Any]],
    editorias_map: dict[int, str],
) -> dict[int, list[dict[str, Any]]]:
    """Agrupa posts por editoria (categoria principal)."""

    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for post in posts:
        categories = post.get("categories", [])
        for cat_id in categories:
            if cat_id in editorias_map:
                grouped[cat_id].append(post)
                break
        else:
            # Post sem editoria mapeada — usar primeira categoria
            if categories:
                grouped[categories[0]].append(post)
    return dict(grouped)


async def _llm_decide_order(
    config: CuradorConfig,
    editoria_summaries: list[dict[str, Any]],
    macrotema_summaries: list[dict[str, Any]],
    preset_name: str,
) -> list[str]:
    """Usa LLM PREMIUM para decidir a ordem dos blocos editoriais.

    Retorna lista ordenada de IDs de bloco.
    """

    prompt_items = {
        "editorias": editoria_summaries,
        "macrotemas": macrotema_summaries,
        "preset": preset_name,
    }

    messages = [
        {
            "role": "system",
            "content": (
                "Você é o editor-chefe do brasileira.news. Decida a ordem dos blocos "
                "editoriais na homepage. Considere: relevância das notícias, diversidade "
                "editorial, engajamento esperado e período do dia. "
                "Retorne APENAS JSON com {\"order\": [\"bloco_id_1\", \"bloco_id_2\", ...]}."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Período: {preset_name}\n"
                f"Blocos disponíveis:\n{json.dumps(prompt_items, ensure_ascii=False)}\n\n"
                "Ordene os blocos do mais importante ao menos importante."
            ),
        },
    ]

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                f"{config.litellm_base_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.litellm_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config.llm_model,
                    "messages": messages,
                    "temperature": 0.2,
                    "max_tokens": 800,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            payload = json.loads(content)
            return payload.get("order", [])
    except Exception as exc:
        logger.warning("LLM de ordenação falhou, usando ordem padrão: %s", exc)
        return []


async def compose_layout(
    config: CuradorConfig,
    scored_posts: list[dict[str, Any]],
    macrotemas: list[dict[str, Any]],
    preset: LayoutPreset,
    current_layout: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compõe layout completo da homepage como JSON de blocos."""

    if not scored_posts:
        logger.warning("Nenhum post para compor layout")
        return _empty_layout(config, preset)

    blocks: list[dict[str, Any]] = []
    used_post_ids: set[int] = set()
    position = 0

    # --- Passo 1: Breaking News ---
    breaking_post = None
    for post in scored_posts:
        if post.get("score_final", 0) >= 90 and _is_very_recent(post):
            breaking_post = post
            break

    if breaking_post:
        blocks.append({
            "id": f"blk_brk_{_uid()}",
            "type": "breaking",
            "position": position,
            "visible": True,
            "config": {
                "post_id": breaking_post["id"],
                "label": "URGENTE",
                "style": "fullwidth_red",
                "auto_expire_minutes": 120,
            },
        })
        used_post_ids.add(breaking_post["id"])
        position += 1

    # --- Passo 2: Manchete principal ---
    manchete_post = None
    sub_posts: list[dict[str, Any]] = []
    for post in scored_posts:
        if post["id"] in used_post_ids:
            continue
        if manchete_post is None:
            manchete_post = post
            used_post_ids.add(post["id"])
        elif len(sub_posts) < 3:
            sub_posts.append(post)
            used_post_ids.add(post["id"])
        else:
            break

    if manchete_post:
        blocks.append({
            "id": f"blk_man_{_uid()}",
            "type": "manchete",
            "position": position,
            "visible": True,
            "config": {
                "principal": manchete_post["id"],
                "submanchetes": [p["id"] for p in sub_posts],
                "style": preset.manchete_style,
            },
        })
        position += 1

    # --- Passo 3: Macrotemas (máx. 3) ---
    macrotema_blocks: list[dict[str, Any]] = []
    for mt in macrotemas[:3]:
        mt_post_ids = [pid for pid in mt["posts"][:4] if pid not in used_post_ids]
        if len(mt_post_ids) < 2:
            continue
        blk_id = f"blk_mt_{mt['tag_id']}"
        block = {
            "id": blk_id,
            "type": "macrotema",
            "position": position,
            "visible": True,
            "config": {
                "tag_id": mt["tag_id"],
                "label": mt["tag_name"],
                "posts": mt_post_ids,
                "style": "highlight_band",
                "temporary": True,
            },
        }
        blocks.append(block)
        macrotema_blocks.append(block)
        for pid in mt_post_ids:
            used_post_ids.add(pid)
        position += 1

    # --- Passo 4: Blocos de editoria ---
    editorias_grouped = _group_by_editoria(scored_posts, config.editorias)

    # Preparar summaries para decisão LLM
    editoria_summaries: list[dict[str, Any]] = []
    editoria_blocks_map: dict[str, dict[str, Any]] = {}
    editorial_count = 0

    for editoria_id, posts_in_ed in editorias_grouped.items():
        # Filtrar posts já usados
        available = [p for p in posts_in_ed if p["id"] not in used_post_ids]
        if len(available) < config.min_posts_per_editoria:
            continue

        blk_id = f"blk_ed_{editoria_id}"
        label = config.editorias.get(editoria_id, f"Editoria {editoria_id}")
        top_posts = available[:5]

        block = {
            "id": blk_id,
            "type": "editoria",
            "position": 0,  # Será ajustado após ordenação
            "visible": True,
            "config": {
                "category_id": editoria_id,
                "label": label,
                "posts": [p["id"] for p in top_posts],
                "style": "grid_5",
                "show_more_link": True,
            },
        }

        editoria_blocks_map[blk_id] = block
        editoria_summaries.append({
            "id": blk_id,
            "label": label,
            "post_count": len(available),
            "top_score": top_posts[0].get("score_final", 0) if top_posts else 0,
            "top_title": top_posts[0].get("title", "")[:60] if top_posts else "",
        })

    # Summaries de macrotemas para LLM
    macrotema_summaries = [
        {
            "id": b["id"],
            "label": b["config"]["label"],
            "post_count": len(b["config"]["posts"]),
        }
        for b in macrotema_blocks
    ]

    # Usar LLM para decidir ordem dos blocos editoriais
    llm_order = await _llm_decide_order(config, editoria_summaries, macrotema_summaries, preset.name)

    # Aplicar ordem do LLM (com fallback: score decrescente)
    if llm_order:
        ordered_ids = [bid for bid in llm_order if bid in editoria_blocks_map]
        # Adicionar blocos que o LLM esqueceu
        remaining = [bid for bid in editoria_blocks_map if bid not in ordered_ids]
        ordered_ids.extend(remaining)
    else:
        # Fallback: ordenar por top_score da editoria
        sorted_eds = sorted(
            editoria_summaries,
            key=lambda e: e.get("top_score", 0),
            reverse=True,
        )
        ordered_ids = [e["id"] for e in sorted_eds]

    # Limitar editorias se preset não exige todas
    if not preset.all_editorias:
        ordered_ids = ordered_ids[:6]

    # Montar blocos na ordem decidida, intercalando publicidade
    for blk_id in ordered_ids:
        block = editoria_blocks_map[blk_id]
        block["position"] = position
        blocks.append(block)
        position += 1
        editorial_count += 1

        # Marcar posts como usados
        for pid in block["config"]["posts"]:
            used_post_ids.add(pid)

        # Inserir publicidade a cada N blocos
        if editorial_count % preset.ad_frequency == 0:
            blocks.append({
                "id": f"blk_ad_{editorial_count}",
                "type": "publicidade",
                "position": position,
                "visible": True,
                "config": {
                    "slot": f"home_mid_{editorial_count}",
                    "size": "728x90",
                },
            })
            position += 1

    # --- Passo 5: Blocos especiais ---

    # Opinião (se proeminente no preset)
    if preset.opiniao_prominent:
        opiniao_cat = 15658  # Opinião & Análise
        opiniao_posts = [
            p for p in scored_posts
            if opiniao_cat in p.get("categories", []) and p["id"] not in used_post_ids
        ]
        if opiniao_posts:
            blocks.append({
                "id": f"blk_opiniao_{_uid()}",
                "type": "colunistas",
                "position": position,
                "visible": True,
                "config": {
                    "posts": [p["id"] for p in opiniao_posts[:4]],
                    "style": "carousel",
                    "label": "Opinião & Análise",
                },
            })
            position += 1

    # Mais Lidas (se proeminente no preset)
    if preset.mais_lidas_prominent:
        mais_lidas_ids = [p["id"] for p in scored_posts[:8]]
        blocks.append({
            "id": f"blk_mais_lidas_{_uid()}",
            "type": "mais_lidas",
            "position": position,
            "visible": True,
            "config": {
                "posts": mais_lidas_ids,
                "style": "numbered_list",
                "label": "Mais Lidas",
            },
        })
        position += 1

    # Newsletter CTA (se proeminente no preset)
    if preset.newsletter_prominent:
        blocks.append({
            "id": f"blk_newsletter_{_uid()}",
            "type": "newsletter",
            "position": position,
            "visible": True,
            "config": {
                "style": "cta_banner",
                "label": "Newsletter brasileira.news",
                "description": "Receba as principais notícias do Brasil direto no seu e-mail",
            },
        })
        position += 1

    # Trending (últimos 5 posts com mais tags)
    trending = sorted(
        [p for p in scored_posts if p["id"] not in used_post_ids],
        key=lambda p: len(p.get("tags", [])),
        reverse=True,
    )[:5]
    if trending:
        blocks.append({
            "id": f"blk_trending_{_uid()}",
            "type": "trending",
            "position": position,
            "visible": True,
            "config": {
                "posts": [p["id"] for p in trending],
                "style": "horizontal_scroll",
                "label": "Em Alta",
            },
        })
        position += 1

    # Publicidade final
    blocks.append({
        "id": f"blk_ad_footer_{_uid()}",
        "type": "publicidade",
        "position": position,
        "visible": True,
        "config": {
            "slot": "home_footer",
            "size": "970x250",
        },
    })
    position += 1

    # --- Passo 6: Montar layout final ---
    cycle_id = str(uuid.uuid4())

    layout: dict[str, Any] = {
        "page_id": config.homepage_page_id,
        "page_type": "homepage",
        "layout_mode": preset.name,
        "updated_at": datetime.now(BST).isoformat(),
        "cycle_id": cycle_id,
        "curador_version": "4.0",
        "blocks": blocks,
    }

    # Respeitar limite máximo de blocos do preset
    if len(blocks) > preset.max_blocks:
        layout["blocks"] = blocks[:preset.max_blocks]

    # Garantir mínimo de blocos (preencher com posts restantes se necessário)
    while len(layout["blocks"]) < preset.min_blocks:
        remaining = [p for p in scored_posts if p["id"] not in used_post_ids]
        if not remaining:
            break
        filler = remaining[:3]
        layout["blocks"].append({
            "id": f"blk_filler_{_uid()}",
            "type": "destaque",
            "position": len(layout["blocks"]),
            "visible": True,
            "config": {
                "posts": [p["id"] for p in filler],
                "style": "compact_list",
                "label": "Também em destaque",
            },
        })
        for p in filler:
            used_post_ids.add(p["id"])

    logger.info("Layout composto: %d blocos (preset: %s)", len(layout["blocks"]), preset.name)
    return layout


def _empty_layout(config: CuradorConfig, preset: LayoutPreset) -> dict[str, Any]:
    """Layout vazio de fallback quando não há posts."""

    return {
        "page_id": config.homepage_page_id,
        "page_type": "homepage",
        "layout_mode": preset.name,
        "updated_at": datetime.now(BST).isoformat(),
        "cycle_id": str(uuid.uuid4()),
        "curador_version": "4.0",
        "blocks": [],
    }
