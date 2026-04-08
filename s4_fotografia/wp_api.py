"""
WordPress REST API Wrappers — Sistema 4 Fotografia
brasileira.news · V2

Funções para interação com WordPress via REST API usando Basic Auth.
Credenciais carregadas de motor_rss/config.py (WP_API_BASE, WP_USER, WP_APP_PASS).
"""

import sys
import logging
from pathlib import Path
from typing import Optional, Any

import requests

# Adiciona o diretório do projeto ao path para imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Importa configurações do motor_rss
try:
    from motor_rss import config as wp_config
except ImportError:
    wp_config = None

# Importa get_or_create_tag do wp_publisher se disponível
try:
    from motor_rss.wp_publisher import get_or_create_tag as _wp_get_or_create_tag
except ImportError:
    _wp_get_or_create_tag = None

logger = logging.getLogger(__name__)


def _safe_json(response):
    """Parse JSON response, handling UTF-8 BOM from WordPress."""
    text = response.text.lstrip("\ufeff")
    import json
    return json.loads(text)

# ─────────────────────────────────────────────────────────────────────────────
# Configuração
# ─────────────────────────────────────────────────────────────────────────────

# Timeout padrão para requisições
REQUEST_TIMEOUT = 30

# Carrega credenciais do motor_rss/config.py ou variáveis de ambiente
import os

if wp_config:
    WP_API_BASE = wp_config.WP_API_BASE
    WP_USER = wp_config.WP_USER
    WP_APP_PASS = wp_config.WP_APP_PASS
else:
    WP_URL = os.environ.get("WP_URL", "https://brasileira.news")
    WP_API_BASE = f"{WP_URL}/wp-json/wp/v2"
    WP_USER = os.environ.get("WP_USER", "iapublicador")
    WP_APP_PASS = os.environ.get("WP_APP_PASS", "")


# ─────────────────────────────────────────────────────────────────────────────
# Session Management
# ─────────────────────────────────────────────────────────────────────────────

_wp_session: Optional[requests.Session] = None


def get_wp_session() -> requests.Session:
    """
    Retorna uma sessão HTTP configurada com Basic Auth para o WordPress.

    A sessão é reutilizada para connection pooling e performance.

    Returns:
        requests.Session configurada com autenticação
    """
    global _wp_session

    if _wp_session is None:
        _wp_session = requests.Session()
        _wp_session.auth = (WP_USER, WP_APP_PASS)
        _wp_session.headers.update({
            "User-Agent": "brasileira.news/s4-fotografia",
            "Accept": "application/json",
        })
        logger.debug("Sessão WordPress inicializada")

    return _wp_session


# ─────────────────────────────────────────────────────────────────────────────
# Post Operations
# ─────────────────────────────────────────────────────────────────────────────


def get_post(post_id: int) -> Optional[dict[str, Any]]:
    """
    Busca um post pelo ID via WordPress REST API.

    Args:
        post_id: ID do post WordPress

    Returns:
        Dict com dados do post ou None se não encontrado
    """
    try:
        session = get_wp_session()
        url = f"{WP_API_BASE}/posts/{post_id}"
        response = session.get(url, timeout=REQUEST_TIMEOUT)

        if response.status_code == 404:
            logger.warning(f"Post {post_id} não encontrado")
            return None

        response.raise_for_status()
        return _safe_json(response)

    except requests.RequestException as e:
        logger.error(f"Erro ao buscar post {post_id}: {e}")
        return None


def get_post_tags(post_id: int) -> list[int]:
    """
    Retorna lista de IDs de tags de um post.

    Args:
        post_id: ID do post WordPress

    Returns:
        Lista de IDs de tags (pode ser vazia)
    """
    post = get_post(post_id)
    if post:
        return post.get("tags", [])
    return []


def update_post_featured_media(post_id: int, media_id: int) -> bool:
    """
    Atualiza a featured_media de um post.

    Args:
        post_id: ID do post WordPress
        media_id: ID da mídia (imagem) a definir como destaque

    Returns:
        True se atualizado com sucesso, False caso contrário
    """
    try:
        session = get_wp_session()
        url = f"{WP_API_BASE}/posts/{post_id}"
        response = session.put(
            url,
            json={"featured_media": media_id},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        logger.info(f"Featured media do post {post_id} atualizada para {media_id}")
        return True

    except requests.RequestException as e:
        logger.error(f"Erro ao atualizar featured_media do post {post_id}: {e}")
        return False


def add_tag_to_post(post_id: int, tag_name: str) -> bool:
    """
    Adiciona uma tag a um post. Cria a tag se não existir.

    Usa get_or_create_tag do motor_rss.wp_publisher se disponível,
    caso contrário implementa lógica inline.

    Args:
        post_id: ID do post WordPress
        tag_name: Nome/slug da tag a adicionar

    Returns:
        True se tag adicionada com sucesso, False caso contrário
    """
    try:
        # 1. Obtém ou cria a tag
        tag_id = _get_or_create_tag_internal(tag_name)
        if not tag_id:
            logger.error(f"Não foi possível obter/criar tag '{tag_name}'")
            return False

        # 2. Busca tags atuais do post
        current_tags = get_post_tags(post_id)
        if tag_id in current_tags:
            logger.debug(f"Post {post_id} já possui tag '{tag_name}'")
            return True

        # 3. Adiciona a nova tag
        new_tags = current_tags + [tag_id]
        session = get_wp_session()
        url = f"{WP_API_BASE}/posts/{post_id}"
        response = session.post(
            url,
            json={"tags": new_tags},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        logger.info(f"Tag '{tag_name}' adicionada ao post {post_id}")
        return True

    except requests.RequestException as e:
        logger.error(f"Erro ao adicionar tag '{tag_name}' ao post {post_id}: {e}")
        return False



def remove_tag_from_post(post_id: int, tag_name: str) -> bool:
    """
    Remove uma tag de um post.

    Args:
        post_id: ID do post WordPress
        tag_name: Nome/slug da tag a remover

    Returns:
        True se tag removida (ou nao existia), False em caso de erro
    """
    try:
        tag_id = _get_tag_id_by_slug(tag_name)
        if not tag_id:
            logger.debug(f"Tag '{tag_name}' nao encontrada - nada a remover do post {post_id}")
            return True

        current_tags = get_post_tags(post_id)
        if tag_id not in current_tags:
            logger.debug(f"Post {post_id} nao possui tag '{tag_name}' - nada a remover")
            return True

        new_tags = [t for t in current_tags if t != tag_id]
        session = get_wp_session()
        url = f"{WP_API_BASE}/posts/{post_id}"
        response = session.post(
            url,
            json={"tags": new_tags},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        logger.info(f"Tag '{tag_name}' removida do post {post_id}")
        return True

    except requests.RequestException as e:
        logger.error(f"Erro ao remover tag '{tag_name}' do post {post_id}: {e}")
        return False

def _get_or_create_tag_internal(tag_name: str) -> Optional[int]:
    """
    Busca tag existente ou cria nova tag via WordPress REST API.

    Tenta usar motor_rss.wp_publisher.get_or_create_tag se disponível.

    Args:
        tag_name: Nome/slug da tag

    Returns:
        ID da tag ou None se falhar
    """
    # Tenta usar a implementação do motor_rss se disponível
    if _wp_get_or_create_tag is not None:
        return _wp_get_or_create_tag(tag_name)

    # Implementação inline como fallback
    try:
        session = get_wp_session()

        # Busca tag existente
        search_url = f"{WP_API_BASE}/tags"
        response = session.get(
            search_url,
            params={"search": tag_name, "per_page": 5},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        tags = _safe_json(response)

        # Verifica se encontrou tag com nome exato
        tag_lower = tag_name.lower().strip()
        for tag in tags:
            if tag.get("name", "").lower().strip() == tag_lower:
                return tag["id"]
            if tag.get("slug", "").lower() == tag_lower:
                return tag["id"]

        # Cria nova tag
        create_response = session.post(
            search_url,
            json={"name": tag_name},
            timeout=REQUEST_TIMEOUT,
        )

        if create_response.status_code in (200, 201):
            new_tag = create_response_json_safe
            logger.info(f"Tag '{tag_name}' criada com ID {new_tag['id']}")
            return new_tag["id"]

        logger.warning(f"Erro ao criar tag '{tag_name}': {create_response.text[:200]}")
        return None

    except requests.RequestException as e:
        logger.error(f"Erro ao buscar/criar tag '{tag_name}': {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Media Operations
# ─────────────────────────────────────────────────────────────────────────────


def get_featured_media_url(post_id: int) -> Optional[str]:
    """
    Resolve o ID de featured_media de um post para a URL da imagem.

    Args:
        post_id: ID do post WordPress

    Returns:
        URL source_url da imagem ou None se não tiver featured_media
    """
    try:
        post = get_post(post_id)
        if not post:
            return None

        media_id = post.get("featured_media")
        if not media_id:
            return None

        # Busca dados da mídia
        session = get_wp_session()
        url = f"{WP_API_BASE}/media/{media_id}"
        response = session.get(url, timeout=REQUEST_TIMEOUT)

        if response.status_code == 404:
            logger.warning(f"Media {media_id} não encontrada")
            return None

        response.raise_for_status()
        media = _safe_json(response)
        return media.get("source_url")

    except requests.RequestException as e:
        logger.error(f"Erro ao buscar featured_media do post {post_id}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Tag-based Queries
# ─────────────────────────────────────────────────────────────────────────────


def get_posts_by_tag(
    tag_slug: str,
    exclude_tag_slug: Optional[str] = None,
    per_page: int = 20,
) -> list[dict[str, Any]]:
    """
    Busca posts filtrados por tag.

    Args:
        tag_slug: Slug da tag a incluir
        exclude_tag_slug: Slug da tag a excluir (opcional)
        per_page: Quantidade máxima de posts

    Returns:
        Lista de dicts com dados dos posts
    """
    try:
        session = get_wp_session()

        # 1. Resolve tag_slug para tag_id
        tag_id = _get_tag_id_by_slug(tag_slug)
        if not tag_id:
            logger.warning(f"Tag '{tag_slug}' não encontrada")
            return []

        # 2. Resolve exclude_tag_slug to ID for server-side filtering
        exclude_tag_id = None
        if exclude_tag_slug:
            exclude_tag_id = _get_tag_id_by_slug(exclude_tag_slug)

        # 3. Busca posts com a tag (usando tags__not_in para filtro server-side)
        url = f"{WP_API_BASE}/posts"
        params = {
            "tags": tag_id,
            "per_page": per_page,
            "status": "publish",
            "_fields": "id,title,tags,featured_media,date",
        }
        # Add server-side exclusion filter if exclude_tag_id was resolved
        if exclude_tag_id:
            params["tags_exclude"] = [exclude_tag_id]
        response = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        posts = _safe_json(response)

        # 4. Safety net: in-memory filter in case server-side filter fails
        if exclude_tag_id:
            posts = [p for p in posts if exclude_tag_id not in p.get("tags", [])]

        return posts

    except requests.RequestException as e:
        logger.error(f"Erro ao buscar posts por tag '{tag_slug}': {e}")
        return []


def _get_tag_id_by_slug(slug: str) -> Optional[int]:
    """
    Busca ID de uma tag pelo slug.

    Args:
        slug: Slug da tag

    Returns:
        ID da tag ou None se não encontrada
    """
    try:
        session = get_wp_session()
        url = f"{WP_API_BASE}/tags"
        response = session.get(
            url,
            params={"slug": slug},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        tags = _safe_json(response)
        if tags:
            return tags[0]["id"]
        return None

    except requests.RequestException as e:
        logger.error(f"Erro ao buscar tag '{slug}': {e}")
        return None
