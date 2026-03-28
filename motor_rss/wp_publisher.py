"""

Publicação de posts via WordPress REST API.

Autenticação via Application Password (Basic Auth).

"""



import logging
import re
import time
import unicodedata

import requests

# HTTP Session para pooling de conexões (bug 5.5)
_wp_session = requests.Session()



import config



logger = logging.getLogger("motor_rss")





def _auth():

    """Retorna tupla de autenticação Basic Auth."""

    return (config.WP_USER, config.WP_APP_PASS)





def _request_with_retry(

    method: str, url: str, retries: int = None, **kwargs

) -> requests.Response | None:

    """Faz request HTTP com retry e backoff exponencial."""

    if retries is None:

        retries = config.WP_RETRY_COUNT

    kwargs.setdefault("timeout", config.HTTP_TIMEOUT)

    kwargs.setdefault("auth", _auth())



    for attempt in range(retries):

        try:

            resp = _wp_session.request(method, url, **kwargs)

            if resp.status_code == 429:
                logger.warning("HTTP 429 em %s. Rate limit atingido. Tentativa %d/%d", url, attempt + 1, retries)
            elif resp.status_code < 500:

                return resp

            logger.warning(

                "HTTP %d em %s (tentativa %d/%d)",

                resp.status_code, url, attempt + 1, retries,

            )

        except Exception as e:
            logger.error(
                "Falha na requisição em %s (tentativa %d/%d): %s | Tipo: %s",
                url, attempt + 1, retries, e, type(e).__name__
            )



        if attempt < retries - 1:

            wait = 2 ** (attempt + 1)

            logger.info("Aguardando %ds antes de retry...", wait)

            time.sleep(wait)



    return None





# ─── Lookup de Categorias e Tags via Banco de Dados ──────
# Usa consulta direta ao DB (rápido) em vez da API REST (lenta).
# WordPress armazena & como &amp; no banco — usamos html.unescape().

import html
import db

_category_cache: dict[str, int] = {}
_category_cache_time = 0
_tag_cache: dict[str, int] = {}
_tag_cache_time = 0
CACHE_TTL = 3600  # 1 hora


def _load_categories_from_db() -> dict[str, int]:
    """Carrega categorias direto do banco com TTL de expiração."""
    global _category_cache, _category_cache_time
    if _category_cache and (time.time() - _category_cache_time < CACHE_TTL):
        return _category_cache
    try:
        raw = db.get_categories()  # {name: term_id}
        _category_cache.clear()
        for name, tid in raw.items():
            normalized = html.unescape(name).lower().strip()
            _category_cache[normalized] = tid
        _category_cache_time = time.time()
        logger.info("Cache de categorias (DB): %d entradas", len(_category_cache))
    except Exception as e:
        logger.warning("Erro ao carregar categorias do DB: %s", e)
    return _category_cache


def _load_tags_from_db() -> dict[str, int]:
    """Carrega tags direto do banco com TTL de expiração."""
    global _tag_cache, _tag_cache_time
    if _tag_cache and (time.time() - _tag_cache_time < CACHE_TTL):
        return _tag_cache
    try:
        raw = db.get_tags()  # {name: term_id}
        _tag_cache.clear()
        for name, tid in raw.items():
            normalized = html.unescape(name).lower().strip()
            _tag_cache[normalized] = tid
        _tag_cache_time = time.time()
        logger.info("Cache de tags (DB): %d entradas", len(_tag_cache))
    except Exception as e:
        logger.warning("Erro ao carregar tags do DB: %s", e)
    return _tag_cache


def get_or_create_category(name: str) -> int | None:
    """Busca categoria no banco ou cria via API se não existir."""
    cats = _load_categories_from_db()
    key = html.unescape(name).lower().strip()

    if key in cats:
        return cats[key]

    # Criar nova categoria via API (caso raro)
    slug = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize('NFKD', key).encode('ascii', 'ignore').decode()).strip("-")
    resp = _request_with_retry(
        "POST",
        f"{config.WP_API_BASE}/categories",
        json={"name": name, "slug": slug},
    )
    if resp and resp.status_code in (200, 201):
        cat_id = resp.json().get("id")
        logger.info("Categoria criada: %s (id=%s)", name, cat_id)
        _category_cache[key] = cat_id
        return cat_id

    logger.warning("Não foi possível obter/criar categoria: %s", name)
    return None


def get_or_create_tag(name: str) -> int | None:
    """Busca tag no banco ou cria via API se não existir."""
    tags = _load_tags_from_db()
    key = html.unescape(name).lower().strip()

    if key in tags:
        return tags[key]

    # Criar nova tag via API
    slug = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize('NFKD', key).encode('ascii', 'ignore').decode()).strip("-")
    resp = _request_with_retry(
        "POST",
        f"{config.WP_API_BASE}/tags",
        json={"name": name, "slug": slug},
    )
    if resp and resp.status_code in (200, 201):
        tag_id = resp.json().get("id")
        logger.info("Tag criada: %s (id=%s)", name, tag_id)
        _tag_cache[key] = tag_id
        return tag_id

    logger.warning("Não foi possível obter/criar tag: %s", name)
    return None





def _resolve_category(name: str) -> list[int]:

    """Resolve nome de categoria para lista de IDs."""

    cat_id = get_or_create_category(name)

    return [cat_id] if cat_id else []





def _resolve_tags(tag_names: list[str]) -> list[int]:

    """Resolve lista de nomes de tags para IDs."""

    ids = []

    for name in tag_names:

        tag_id = get_or_create_tag(name.strip())

        if tag_id:

            ids.append(tag_id)

    return ids





def publish_post(

    title: str,

    content: str,

    excerpt: str,

    category_name: str,

    tag_names: list[str],

    featured_media: int | None,

    push_notification: str = "",
    prompt_imagem: str = "",
    legenda_imagem: str = "",
    seo_title: str = "",

    seo_description: str = "",

) -> int | None:

    """

    Publica um post no WordPress via REST API.

    Retorna post_id ou None se falhar.

    """

    category_ids = _resolve_category(category_name)

    tag_ids = _resolve_tags(tag_names)



    post_data = {

        "title": title,

        "content": content,

        "excerpt": excerpt,

        "status": "publish",

        "categories": category_ids,

        "tags": tag_ids,

    }



    if featured_media:

        post_data["featured_media"] = featured_media



    # Meta SEO compatível com Yoast e AIOSEO

    meta = {}

    if seo_title:

        meta["_yoast_wpseo_title"] = seo_title

        meta["_aioseo_title"] = seo_title

    if seo_description:

        meta["_yoast_wpseo_metadesc"] = seo_description

        meta["_aioseo_description"] = seo_description

    if meta:

        post_data["meta"] = meta



    resp = _request_with_retry(

        "POST",

        f"{config.WP_API_BASE}/posts",

        json=post_data,

    )



    if resp is not None and resp.status_code in (200, 201):

        post_id = resp.json().get("id")

        post_link = resp.json().get("link", "")

        logger.info(

            "Post publicado: id=%s | %s | %s", post_id, title[:60], post_link

        )

        return post_id

    elif resp is not None:

        logger.error(

            "Falha ao publicar (HTTP %d): %s — %s",

            resp.status_code, title[:60], resp.text[:300],

        )

    else:

        logger.error("Falha ao publicar (sem resposta): %s", title[:60])



    return None

