"""
Operações Supabase — Sistema 4 Fotografia
brasileira.news · V2

Singleton Supabase client e funções de persistência para:
- Histórico de buscas de imagem
- Registro de imagens usadas
- Estatísticas de queries efetivas
- Contexto editorial (leitura de s3_editorial_context)
- Dead letter tracking
"""

import os
import sys
import time
import logging
from pathlib import Path
from typing import Optional, Any

# Adiciona o diretório do projeto ao path para imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Singleton Supabase Client
# ─────────────────────────────────────────────────────────────────────────────

_supabase_client = None


def get_supabase_client():
    """
    Retorna singleton do cliente Supabase.

    Carrega credenciais das variáveis de ambiente:
    - SUPABASE_URL: URL do projeto Supabase
    - SUPABASE_SERVICE_KEY: Service role key para acesso completo

    Returns:
        Supabase client instance

    Raises:
        ValueError: Se as variáveis de ambiente não estiverem configuradas
    """
    global _supabase_client

    if _supabase_client is None:
        try:
            from supabase import create_client
        except ImportError:
            logger.error("Pacote 'supabase' não instalado. Execute: pip install supabase")
            raise

        supabase_url = os.environ.get("SUPABASE_URL")
        supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")

        if not supabase_url or not supabase_key:
            raise ValueError(
                "Variáveis SUPABASE_URL e SUPABASE_SERVICE_KEY devem estar configuradas"
            )

        _supabase_client = create_client(supabase_url, supabase_key)
        logger.info("Cliente Supabase inicializado")

    return _supabase_client


# ─────────────────────────────────────────────────────────────────────────────
# Log de Buscas de Imagem (s4_image_search_history)
# ─────────────────────────────────────────────────────────────────────────────


def log_image_search(
    post_id: int,
    search_query: str,
    source_tried: str,
    source_order: int,
    results_found: int,
    image_selected: Optional[str],
    image_applied: bool,
    quality_score: Optional[float],
    rejection_reason: Optional[str],
    processing_time_ms: Optional[int] = None,
) -> bool:
    """
    Registra uma tentativa de busca de imagem em s4_image_search_history.

    Args:
        post_id: ID do post WordPress
        search_query: Query de busca utilizada
        source_tried: Nome da fonte (agencia_brasil, flickr, etc.)
        source_order: Posição na fila de fontes (1=primeira)
        results_found: Quantidade de resultados encontrados
        image_selected: URL da imagem selecionada (None se não encontrou)
        image_applied: True se esta imagem foi aplicada ao post
        quality_score: Score de qualidade 0-10 (avaliação LLM)
        rejection_reason: Motivo de rejeição se não aplicada
        processing_time_ms: Tempo de processamento em milissegundos

    Returns:
        True se inserido com sucesso, False caso contrário
    """
    try:
        client = get_supabase_client()
        data = {
            "post_id": post_id,
            "search_query": search_query,
            "source_tried": source_tried,
            "source_order": source_order,
            "results_found": results_found,
            "image_selected": image_selected,
            "image_applied": image_applied,
            "quality_score": quality_score,
            "rejection_reason": rejection_reason,
        }
        if processing_time_ms is not None:
            data["processing_time_ms"] = processing_time_ms

        client.table("s4_image_search_history").insert(data).execute()
        return True

    except Exception as e:
        logger.warning(f"log_image_search falhou para post {post_id}: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Registro de Imagens Usadas (s4_used_images)
# ─────────────────────────────────────────────────────────────────────────────


def upsert_used_image(
    image_url: str,
    image_hash: Optional[str],
    post_id: int,
    source: str,
    author: Optional[str] = None,
    license_type: Optional[str] = None,
) -> bool:
    """
    Registra ou atualiza uma imagem usada em s4_used_images via RPC upsert.

    Args:
        image_url: URL completa da imagem
        image_hash: Hash MD5 da URL (para busca rápida)
        post_id: ID do post WordPress onde foi usada
        source: Origem da imagem (agencia_brasil, flickr, etc.)
        author: Autor/crédito da imagem
        license_type: Tipo de licença (CC BY, domínio público, etc.)

    Returns:
        True se operação bem-sucedida, False caso contrário
    """
    try:
        client = get_supabase_client()
        client.rpc(
            "upsert_used_image",
            {
                "p_image_url": image_url,
                "p_image_hash": image_hash or "",
                "p_post_id": post_id,
                "p_source": source,
                "p_author": author or "",
                "p_license": license_type or "",
            },
        ).execute()
        return True

    except Exception as e:
        logger.warning(f"upsert_used_image falhou para {image_url[:50]}: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Estatísticas de Queries Efetivas (s4_effective_queries)
# ─────────────────────────────────────────────────────────────────────────────


def update_query_stats(
    category: str,
    topic: str,
    query: str,
    source: str,
    success: bool,
) -> bool:
    """
    Atualiza estatísticas de query efetiva via RPC update_query_stats.

    Args:
        category: Slug da categoria (politica, economia, etc.)
        topic: Tópico/entidade principal
        query: Padrão de query usado
        source: Fonte onde foi tentada
        success: True se a query retornou imagem adequada

    Returns:
        True se operação bem-sucedida, False caso contrário
    """
    try:
        client = get_supabase_client()
        client.rpc(
            "update_query_stats",
            {
                "p_category": category,
                "p_topic": topic,
                "p_query": query,
                "p_source": source,
                "p_success": success,
            },
        ).execute()
        return True

    except Exception as e:
        logger.warning(f"update_query_stats falhou: {e}")
        return False


def get_effective_queries(
    category: str,
    entities: list[str],
) -> list[dict[str, Any]]:
    """
    Busca queries que funcionaram bem para categoria/entidades via RPC.

    Args:
        category: Slug da categoria
        entities: Lista de entidades principais do artigo

    Returns:
        Lista de dicts com query_pattern, source, success_rate (top 3)
    """
    try:
        client = get_supabase_client()
        result = client.rpc(
            "get_effective_queries_for_context",
            {
                "p_category": category,
                "p_entities": entities[:5] if entities else [],
            },
        ).execute()
        return result.data[:3] if isinstance(result.data, list) and result.data else []

    except Exception as e:
        logger.warning(f"get_effective_queries falhou: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Posts Aguardando Foto (via WordPress REST API)
# ─────────────────────────────────────────────────────────────────────────────


def get_posts_awaiting_photo(per_page: int = 20) -> list[dict[str, Any]]:
    """
    Busca posts publicados nas últimas 24h SEM imagem destacada.
    
    Estratégia: buscar posts recentes sem featured_media, excluindo os que
    já foram marcados como 'sem-imagem' ou 's4-falha' (já tentados).
    Não depende mais da tag 'revisado' do S3.
    
    Prioridade: posts mais recentes primeiro.
    """
    try:
        from .wp_api import get_wp_session, _get_tag_id_by_slug
        import os
        import json
        try:
            from motor_rss.config import WP_API_BASE
        except ImportError:
            WP_API_BASE = os.getenv("WP_API_URL", "https://brasileira.news/wp-json/wp/v2")

        session = get_wp_session()
        
        # Apenas últimas 24h, mais recentes primeiro
        from datetime import datetime, timedelta, timezone
        after_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S")
        
        # Resolver IDs de tags a excluir (posts já processados)
        exclude_tag_ids = []
        for slug in ["foto-verificada", "sem-imagem", "s4-falha"]:
            tid = _get_tag_id_by_slug(slug)
            if tid:
                exclude_tag_ids.append(tid)
        
        params = {
            "per_page": per_page,
            "status": "publish",
            "after": after_24h,
            "orderby": "date",
            "order": "desc",
            "_fields": "id,title,tags,featured_media,date",
        }
        
        if exclude_tag_ids:
            params["tags_exclude"] = ",".join(str(t) for t in exclude_tag_ids)
        
        response = session.get(f"{WP_API_BASE}/posts", params=params, timeout=30)
        response.raise_for_status()
        posts = json.loads(response.text.lstrip("\ufeff"))
        
        # Filtrar apenas posts SEM featured_media (= 0 ou ausente)
        sem_foto = [p for p in posts if not p.get("featured_media")]
        
        logger.info(
            f"get_posts_awaiting_photo: {len(posts)} recentes, "
            f"{len(sem_foto)} sem foto (excluídas {len(exclude_tag_ids)} tags)"
        )
        
        return sem_foto

    except Exception as e:
        logger.error(f"get_posts_awaiting_photo falhou: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Contexto Editorial (s3_editorial_context)
# ─────────────────────────────────────────────────────────────────────────────


def get_editorial_context(post_id: int) -> Optional[dict[str, Any]]:
    """
    Busca contexto editorial do Sistema 3 para um post.

    Args:
        post_id: ID do post WordPress

    Returns:
        Dict com article_summary, main_entities, main_topics, quality_score, category_slug
        ou None se não encontrado
    """
    try:
        client = get_supabase_client()
        result = (
            client.table("s3_editorial_context")
            .select("*")
            .eq("post_id", post_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    except Exception as e:
        logger.error(f"get_editorial_context({post_id}) falhou: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Dead Letter Tracking
# ─────────────────────────────────────────────────────────────────────────────


def mark_dead_letter(post_id: int, reason: str) -> bool:
    """
    Marca um post como dead letter (falha permanente após múltiplas tentativas).

    Args:
        post_id: ID do post WordPress
        reason: Motivo da falha permanente

    Returns:
        True se marcado com sucesso, False caso contrário
    """
    try:
        client = get_supabase_client()
        client.table("s4_dead_letter").insert(
            {
                "post_id": post_id,
                "reason": reason,
                "system_id": 4,
            }
        ).execute()
        logger.warning(f"Post {post_id} marcado como dead letter: {reason}")
        return True

    except Exception as e:
        logger.error(f"mark_dead_letter({post_id}) falhou: {e}")
        return False


def get_failure_count(post_id: int) -> int:
    """
    Conta quantas falhas de busca de imagem um post teve.

    Args:
        post_id: ID do post WordPress

    Returns:
        Número de tentativas falhas (image_applied=False)
    """
    try:
        client = get_supabase_client()
        result = (
            client.table("s4_image_search_history")
            .select("id", count="exact")
            .eq("post_id", post_id)
            .eq("image_applied", False)
            .execute()
        )
        return result.count if result.count else 0

    except Exception as e:
        logger.warning(f"get_failure_count({post_id}) falhou: {e}")
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# Funções Auxiliares
# ─────────────────────────────────────────────────────────────────────────────


def check_image_used(image_url: str) -> bool:
    """
    Verifica se uma URL de imagem já foi usada em outro post.

    Args:
        image_url: URL da imagem a verificar

    Returns:
        True se já foi usada, False caso contrário
    """
    try:
        client = get_supabase_client()
        result = (
            client.table("s4_used_images")
            .select("id")
            .eq("image_url", image_url)
            .limit(1)
            .execute()
        )
        return len(result.data) > 0

    except Exception as e:
        logger.warning(f"check_image_used falhou: {e}")
        return False


def check_history(post_id: int, source: str) -> Optional[dict[str, Any]]:
    """
    Verifica se um post já teve tentativa em uma fonte específica.

    Args:
        post_id: ID do post WordPress
        source: Nome da fonte (agencia_brasil, flickr, etc.)

    Returns:
        Dict com dados da tentativa anterior ou None
    """
    try:
        client = get_supabase_client()
        result = (
            client.table("s4_image_search_history")
            .select("*")
            .eq("post_id", post_id)
            .eq("source_tried", source)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    except Exception as e:
        logger.warning(f"check_history falhou: {e}")
        return None
