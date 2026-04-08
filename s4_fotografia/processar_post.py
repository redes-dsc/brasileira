"""
Processamento de Post Individual — Sistema 4 Fotografia
brasileira.news · V2

Lógica central de curadoria fotográfica para um único post.
Implementa Fast Path (verificação de fonte pública) e Full Search Path.
"""

import sys
import time
import logging
from pathlib import Path
from typing import Optional

# Adiciona o diretório do projeto ao path para imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from s4_fotografia.wp_api import (
    get_post,
    get_featured_media_url,
    add_tag_to_post,
    remove_tag_from_post,
    update_post_featured_media,
)
from s4_fotografia.supabase_ops import (
    get_editorial_context,
    get_failure_count,
    mark_dead_letter,
    log_image_search,
)
from s4_fotografia.is_fonte_publica import is_fonte_publica
from s4_fotografia.build_search_query import build_search_query
from s4_fotografia.find_image import find_image_with_retry
from s4_fotografia.wp_upload import process_and_upload

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────────────────────

MAX_FAILURES = 33  # 3 ciclos completos × 11 fontes por ciclo
TAG_FOTO_VERIFICADA = "foto-verificada"
TAG_SEM_IMAGEM = "sem-imagem"
TAG_S4_FALHA = "s4-falha"


# ─────────────────────────────────────────────────────────────────────────────
# Xinhua Fast-Path
# ─────────────────────────────────────────────────────────────────────────────


def _check_xinhua_image(post_content: str, post_id: int) -> Optional[dict]:
    """
    Verifica se o post já tem imagem da Xinhua no conteúdo.
    Se sim, retorna a imagem para uso direto (skip pipeline de busca).
    """
    import re
    
    xinhua_pattern = re.compile(
        r'https?://(?:portuguese\.)?news\.cn/\d{8}/[a-f0-9]+/[a-f0-9]+\.(?:jpg|JPG|jpeg|png)',
        re.IGNORECASE
    )
    
    match = xinhua_pattern.search(post_content)
    if match:
        return {
            "url": match.group(0),
            "source": "xinhua_original",
            "author": "Xinhua News Agency",
            "license": "Xinhua — uso editorial",
            "description": "",
            "score": 0.95,  # Alta prioridade — imagem original do artigo
        }
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Função Principal
# ─────────────────────────────────────────────────────────────────────────────


def processar_post(post_id: int) -> dict:
    """
    Process a single post for image curation.

    Implements two paths:
    1. FAST PATH: If post has featured_media from public source, just add tag
    2. FULL SEARCH: Search for image using LLM-generated query across 11 sources

    Args:
        post_id: WordPress post ID to process

    Returns:
        {
            'post_id': int,
            'status': str,  # 'foto-verificada' | 'sem-imagem' | 'erro' | 'skip-public'
            'image_url': str | None,
            'source': str | None,
            'processing_time_ms': int
        }
    """
    start_time = time.time()
    result = {
        "post_id": post_id,
        "status": "erro",
        "image_url": None,
        "source": None,
        "processing_time_ms": 0,
    }

    try:
        logger.info(f"[processar_post] Iniciando processamento do post {post_id}")

        # ─────────────────────────────────────────────────────────────────────
        # FAST PATH: Verificação de imagem existente
        # ─────────────────────────────────────────────────────────────────────

        post = get_post(post_id)
        if not post:
            logger.error(f"[processar_post] Post {post_id} não encontrado")
            result["status"] = "erro"
            result["processing_time_ms"] = _elapsed_ms(start_time)
            return result

        # ─────────────────────────────────────────────────────────────────────
        # XINHUA FAST PATH: Check for original Xinhua image in content
        # ─────────────────────────────────────────────────────────────────────
        post_content = post.get("content", {}).get("rendered", "")
        xinhua_img = _check_xinhua_image(post_content, post_id)
        if xinhua_img:
            logger.info(f"[processar_post] Post {post_id}: imagem Xinhua original encontrada")
            
            # Upload the Xinhua image to WordPress
            media_id = process_and_upload(
                image_url=xinhua_img["url"],
                caption_text=xinhua_img["description"],
                author=xinhua_img["author"],
                license_type=xinhua_img["license"],
            )
            
            if media_id:
                # Update featured media
                update_success = update_post_featured_media(post_id, media_id)
                
                if update_success:
                    add_tag_to_post(post_id, TAG_FOTO_VERIFICADA)
                    remove_tag_from_post(post_id, TAG_SEM_IMAGEM)  # limpar tag conflitante
                    
                    result["status"] = "foto-verificada"
                    result["image_url"] = xinhua_img["url"]
                    result["source"] = xinhua_img["source"]
                    result["processing_time_ms"] = _elapsed_ms(start_time)
                    
                    logger.info(
                        f"[processar_post] Sucesso! Post {post_id} recebeu imagem Xinhua "
                        f"(media_id={media_id})"
                    )
                    return result
            
            # If Xinhua upload failed, continue to normal pipeline
            logger.warning(
                f"[processar_post] Falha no upload da imagem Xinhua para post {post_id}. "
                f"Prosseguindo para pipeline normal."
            )

        featured_media = post.get("featured_media")

        if featured_media:
            # Post já tem imagem — verificar se é fonte pública
            image_url = get_featured_media_url(post_id)

            if image_url and is_fonte_publica(image_url):
                # Imagem é de fonte pública — Fast Path Success!
                logger.info(
                    f"[processar_post] Fast Path: post {post_id} já tem imagem de fonte pública"
                )
                add_tag_to_post(post_id, TAG_FOTO_VERIFICADA)
                remove_tag_from_post(post_id, TAG_SEM_IMAGEM)  # limpar tag conflitante

                result["status"] = "skip-public"
                result["image_url"] = image_url
                result["source"] = "fonte-publica-existente"
                result["processing_time_ms"] = _elapsed_ms(start_time)
                return result

            # Imagem não é de fonte pública ou URL inválida — continuar para Full Search
            logger.info(
                f"[processar_post] Post {post_id} tem imagem, mas não é fonte pública. "
                f"Prosseguindo para busca completa."
            )

        # ─────────────────────────────────────────────────────────────────────
        # FULL SEARCH PATH
        # ─────────────────────────────────────────────────────────────────────

        # 1. Buscar contexto editorial do Sistema 3
        editorial_context = get_editorial_context(post_id)

        if not editorial_context:
            logger.warning(
                f"[processar_post] Sem contexto editorial para post {post_id}. "
                f"Tentando busca básica com título."
            )
            # Fallback: usar título do post como query
            post_title = _extract_title(post)
            category_slug = _extract_category_slug(post)
            
            # Sem contexto do S3 — montar contexto mínimo a partir do post
            # e usar LLM para gerar query inteligente de 3-6 palavras
            logger.warning(
                f"[processar_post] Sem contexto editorial para post {post_id}. "
                f"Gerando query via LLM a partir do título."
            )
            editorial_context = {
                "main_entities": [],
                "main_topics": [post_title] if post_title else [],
                "article_summary": post_title or "",
                "category_slug": category_slug,
                "source_url": "",
            }
            # Usar LLM mesmo sem contexto completo — melhor que título truncado
            try:
                search_query = build_search_query(editorial_context, category_slug)
                logger.info(f"[processar_post] Query LLM (sem contexto S3): '{search_query}'")
            except Exception as e:
                logger.warning(f"[processar_post] Falha no build_search_query: {e}. Usando título.")
                search_query = post_title[:50] if post_title else "Brasil"
        else:
            # Extrair category_slug do contexto ou do post
            category_slug = editorial_context.get("category_slug") or _extract_category_slug(post)

            # 2. Construir query de busca via LLM
            search_query = build_search_query(editorial_context, category_slug)
            logger.info(f"[processar_post] Query gerada: '{search_query}'")

        # 3. Buscar imagem via pipeline 3-fases
        image_result = find_image_with_retry(
            initial_query=search_query,
            post_id=post_id,
            category_slug=category_slug,
            editorial_context=editorial_context,
        )

        if image_result and image_result.get("media_id"):
            # Imagem encontrada e uploaded!
            media_id = image_result["media_id"]

            # 4a. Atualizar featured_media do post
            update_success = update_post_featured_media(post_id, media_id)

            if update_success:
                # 4b. Adicionar tag foto-verificada
                add_tag_to_post(post_id, TAG_FOTO_VERIFICADA)
                remove_tag_from_post(post_id, TAG_SEM_IMAGEM)  # limpar tag conflitante

                result["status"] = "foto-verificada"
                result["image_url"] = image_result.get("url")
                result["source"] = image_result.get("source")
                result["processing_time_ms"] = _elapsed_ms(start_time)

                logger.info(
                    f"[processar_post] Sucesso! Post {post_id} recebeu imagem de "
                    f"{image_result.get('source')} (media_id={media_id})"
                )
                return result

            else:
                logger.error(
                    f"[processar_post] Falha ao atualizar featured_media do post {post_id}"
                )
                add_tag_to_post(post_id, TAG_S4_FALHA)
                result["status"] = "erro"
                result["processing_time_ms"] = _elapsed_ms(start_time)
                return result

        else:
            # Pipeline exaurido — sem imagem adequada
            logger.warning(
                f"[processar_post] Nenhuma imagem encontrada para post {post_id}"
            )
            add_tag_to_post(post_id, TAG_SEM_IMAGEM)

            result["status"] = "sem-imagem"
            result["processing_time_ms"] = _elapsed_ms(start_time)
            return result

    except Exception as e:
        logger.error(f"[processar_post] Erro no post {post_id}: {e}", exc_info=True)
        result["status"] = "erro"
        result["processing_time_ms"] = _elapsed_ms(start_time)

        # ─────────────────────────────────────────────────────────────────────
        # DEAD LETTER HANDLING
        # ─────────────────────────────────────────────────────────────────────

        return _handle_failure(post_id, e, result)

    # Fallback return
    result["processing_time_ms"] = _elapsed_ms(start_time)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Funções Auxiliares
# ─────────────────────────────────────────────────────────────────────────────


def _handle_failure(post_id: int, exception: Exception, result: dict) -> dict:
    """
    Handle processing failures with dead letter logic.

    After MAX_FAILURES consecutive failures, marks post as dead letter.

    Args:
        post_id: WordPress post ID
        exception: The exception that occurred
        result: Current result dict to update

    Returns:
        Updated result dict

    Raises:
        Exception: Re-raises if failure count < MAX_FAILURES (for retry)
    """
    failure_count = get_failure_count(post_id)
    # Increment implicitly happens via log_image_search with image_applied=False
    # but we need to count existing failures

    # We treat this error as an additional failure
    total_failures = failure_count + 1

    logger.warning(
        f"[processar_post] Post {post_id} falha #{total_failures} de {MAX_FAILURES}"
    )

    if total_failures >= MAX_FAILURES:
        # Marca como dead letter
        error_reason = f"Falha permanente após {total_failures} tentativas: {str(exception)[:200]}"
        add_tag_to_post(post_id, TAG_S4_FALHA)
        mark_dead_letter(post_id, error_reason)

        result["status"] = "erro"
        logger.error(f"[processar_post] Post {post_id} marcado como dead letter")
        return result

    # Retry no próximo ciclo — re-raise para que o worker saiba
    raise exception


def _elapsed_ms(start_time: float) -> int:
    """Calculate elapsed time in milliseconds since start_time."""
    return int((time.time() - start_time) * 1000)


def _extract_title(post: dict) -> str:
    """Extract post title from WP REST API response."""
    title_obj = post.get("title", {})
    if isinstance(title_obj, dict):
        return title_obj.get("rendered", "")
    return str(title_obj) if title_obj else ""


def _extract_category_slug(post: dict) -> str:
    """Extrai o slug da categoria principal do post."""
    categories = post.get("categories", [])
    if not categories:
        return "geral"
    
    try:
        from s4_fotografia.wp_api import get_wp_session
        session = get_wp_session()
        # Get WP_API_BASE from the same source as wp_api.py
        import os
        try:
            from motor_rss.config import WP_API_BASE
        except ImportError:
            WP_API_BASE = os.getenv("WP_API_URL", "https://brasileira.news/wp-json/wp/v2")
        
        resp = session.get(
            f"{WP_API_BASE}/categories/{categories[0]}",
            timeout=10
        )
        if resp.status_code == 200:
            import json as _j; return _j.loads(resp.text.lstrip("\ufeff")).get("slug", "geral")
    except Exception as e:
        logger.warning(f"[_extract_category_slug] Falha ao resolver categoria: {e}")
    
    return "geral"
