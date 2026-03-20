"""
Publicação especializada para matérias consolidadas.
Adiciona tags especiais, bloco de fontes, e registra no controle.
"""

import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path("/home/bitnami/motor_rss")))
sys.path.insert(0, str(Path("/home/bitnami")))

import config
import db
import wp_publisher
import image_handler

from config_consolidado import (
    ID_REDACAO, TAG_CONSOLIDADA, TAG_HOME_ESPECIAL,
    FEED_NAME_CONSOLIDADA, DRY_RUN, PUBLISH_AS_DRAFT,
)

logger = logging.getLogger("motor_consolidado")


def _build_fontes_html(sources: list[dict]) -> str:
    """Constrói bloco HTML das fontes consultadas para o final do artigo."""
    if not sources:
        return ""

    items = []
    seen = set()
    for src in sources:
        name = src.get("portal_name", "")
        url = src.get("url", "")
        if name in seen:
            continue
        seen.add(name)
        if url:
            items.append(
                f'<li><a href="{url}" target="_blank" rel="nofollow">{name}</a></li>'
            )
        else:
            items.append(f"<li>{name}</li>")

    return (
        "\n\n<h2>Fontes consultadas</h2>\n"
        "<ul>\n" + "\n".join(items) + "\n</ul>"
    )


def _get_image_for_consolidated(article: dict, sources: list[dict]) -> int | None:
    """
    Obtém imagem para a matéria consolidada usando o Curador Unificado.
    """
    title = article.get("titulo", "")
    keywords = " ".join(article.get("tags", [])[:3]) if article.get("tags") else title

    # Preparar importação do nosso novo curador unificado
    import sys
    from pathlib import Path
    try:
        sys.path.insert(0, str(Path("/home/bitnami")))
        from curador_imagens_unificado import get_curador, upload_to_wordpress, is_official_source
    except Exception as e:
        logger.error(f"Não foi possível importar curador_imagens_unificado: {e}")
        return None

    # Tentar usar a imagem original informada pela fonte principal apenas se for fonte oficial (Evitar Copyright Comercial)
    for src in sources:
        img_url = src.get("imagem", "")
        src_url = src.get("url", "")
        if img_url and is_official_source(src_url):
            logger.info("Usando imagem explícita de fonte OFICIAL (%s): %s", src.get("portal_name", "Fonte"), img_url[:60])
            safe_name = re.sub(r"[^a-z0-9]+", "-", title.lower().strip())[:50]
            from urllib.parse import urlparse
            domain = urlparse(src_url).netloc
            caption = f"Reprodução Livre / {domain}"
            media_id = upload_to_wordpress(img_url, f"consolidada-{safe_name}", alt_text=title, caption=caption)
            if media_id:
                return media_id

    # Fallback para o Curador Unificado
    first_source_url = sources[0].get("url", "") if sources else ""
    first_html = sources[0].get("html_content", "") if sources else ""
    
    # Se html_content está vazio mas a fonte é oficial, buscar o HTML para Tier 1 extrair og:image
    if not first_html and first_source_url and is_official_source(first_source_url):
        try:
            import requests as _req
            _resp = _req.get(first_source_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if _resp.status_code == 200:
                first_html = _resp.text
                logger.info("[IMAGEM] HTML da fonte oficial raspado para Tier 1 (%d bytes)", len(first_html))
        except Exception as _e:
            logger.warning("[IMAGEM] Falha ao raspar HTML oficial: %s", _e)
    
    # Para fontes NÃO oficiais, usar campos de imagem já gerados pelo Sintetizador (LLM premium)
    explicit_gov = ""
    explicit_commons = ""
    explicit_block_stock = None
    
    if is_official_source(first_source_url):
        logger.info("[IMAGEM] Fonte oficial na consolidada. Tier 1 resolverá.")
    else:
        # Sintetizador SEMPRE usa TIER_CONSOLIDATOR (Claude/GPT-4o) — confiar nos campos
        explicit_gov = article.get("imagem_busca_gov", "")
        explicit_commons = article.get("imagem_busca_commons", "")
        explicit_block_stock = article.get("block_stock_images")

        if explicit_gov:
            logger.info("[IMAGEM] Sintetizador premium — confiando: gov='%s'", explicit_gov)
        else:
            # Fallback: campos ausentes, chamar Editor Premium
            logger.info("[IMAGEM] Sintetizador não retornou campos. Editor Premium...")
            sys.path.insert(0, str(Path("/home/bitnami/motor_rss")))
            import llm_router
            photo_prompt = (
                f"Você é o Editor de Fotografia do portal Brasileira.News.\n"
                f"Para PESSOAS: busque nome + status jornalístico (preso, ministro, réu). Nunca detalhes de cena.\n"
                f"Para LOCAIS/EVENTOS sem pessoa: busque o nome do local.\n\n"
                f"Título: {title}\n"
                f"Categoria: {article.get('categoria', '')}\n"
                f"Excerpt: {article.get('excerpt', '')}\n"
                f"Tags: {', '.join(article.get('tags', []))}\n\n"
                f"Retorne APENAS JSON com:\n"
                f"imagem_busca_gov: nome da pessoa (+ status) ou nome do local. Máx 3 palavras.\n"
                f"imagem_busca_commons: nome formal/enciclopédico para Wikimedia\n"
                f"block_stock_images: true se factual, false se abstrato"
            )
            try:
                photo_result, photo_provider = llm_router.call_llm(
                    system_prompt="Você é um editor de fotografia jornalística. JSON válido apenas.",
                    user_prompt=photo_prompt,
                    tier=llm_router.TIER_PHOTO_EDITOR,
                    parse_json=True,
                )
                if photo_result and isinstance(photo_result, dict):
                    explicit_gov = photo_result.get("imagem_busca_gov", "")
                    explicit_commons = photo_result.get("imagem_busca_commons", "")
                    explicit_block_stock = photo_result.get("block_stock_images", True)
                    logger.info("[IMAGEM] Editor Foto (%s): gov='%s'", photo_provider, explicit_gov)
            except Exception as e:
                logger.warning("[IMAGEM] Falha Editor Foto: %s", e)

    curador = get_curador()
    media_id, _ = curador.get_featured_image(
        html_content=first_html,
        source_url=first_source_url,
        title=title,
        keywords=keywords,
        explicit_gov_query=explicit_gov,
        explicit_commons_query=explicit_commons,
        explicit_block_stock=explicit_block_stock
    )
    
    if media_id:
        return media_id

    logger.warning("Nenhuma imagem encontrada para consolidada: %s", title[:60])
    return None


def publish_consolidated(article: dict, sources: list[dict]) -> int | None:
    """
    Publica matéria consolidada no WordPress.
    
    - Tags: LLM tags + "consolidada" + "home-especial"
    - Categoria: via LLM
    - Autor: Redação Brasileira (ID 4)
    - Imagem: da fonte principal ou Unsplash
    - Registra em rss_control com feed_name="consolidada"
    
    Retorna post_id ou None.
    """
    title = article.get("titulo", "")
    content = article.get("conteudo", "")
    excerpt = article.get("excerpt", "")
    category = article.get("categoria", "Política & Poder")
    tags = article.get("tags", [])
    seo_title = article.get("seo_title", "")
    seo_description = article.get("seo_description", "")
    llm_provider = article.get("_llm_provider", "unknown")

    if not title or not content:
        logger.error("Artigo sem título ou conteúdo — ignorando")
        return None

    # Verificar se o conteúdo já tem bloco de fontes, se não, adicionar
    if "Fontes consultadas" not in content:
        content += _build_fontes_html(sources)

    # Tags especiais
    if TAG_CONSOLIDADA not in tags:
        tags.append(TAG_CONSOLIDADA)
    if TAG_HOME_ESPECIAL not in tags:
        tags.append(TAG_HOME_ESPECIAL)

    # DRY RUN
    if DRY_RUN:
        logger.info("[DRY RUN] Publicaria: '%s' | Tags: %s | Cat: %s", title[:60], tags, category)
        return -1  # ID fictício

    # Obter imagem
    media_id = _get_image_for_consolidated(article, sources)

    # Publicar
    logger.info("Publicando consolidada: '%s'", title[:60])

    # Resolver categoria e tags
    category_ids = wp_publisher._resolve_category(category)
    tag_ids = wp_publisher._resolve_tags(tags)

    # Montar post data
    import requests as req

    status = "draft" if PUBLISH_AS_DRAFT else "publish"

    post_data = {
        "title": title,
        "content": content,
        "excerpt": excerpt,
        "status": status,
        "categories": category_ids,
        "tags": tag_ids,
        "author": ID_REDACAO,
    }

    if media_id:
        post_data["featured_media"] = media_id

    # Meta SEO
    meta = {}
    if seo_title:
        meta["_yoast_wpseo_title"] = seo_title
        meta["_aioseo_title"] = seo_title
    if seo_description:
        meta["_yoast_wpseo_metadesc"] = seo_description
        meta["_aioseo_description"] = seo_description
    if meta:
        post_data["meta"] = meta

    try:
        resp = req.post(
            f"{config.WP_API_BASE}/posts",
            auth=(config.WP_USER, config.WP_APP_PASS),
            json=post_data,
            timeout=30,
        )

        if resp.status_code in (200, 201):
            post_id = resp.json().get("id")
            post_link = resp.json().get("link", "")
            logger.info(
                "Consolidada publicada: id=%s | %s | %s | status=%s",
                post_id, title[:60], post_link, status,
            )

            # Registrar no controle
            source_urls = ",".join([s.get("url", "") for s in sources[:3]])
            db.register_published(
                post_id=post_id,
                source_url=source_urls[:2048],
                feed_name=FEED_NAME_CONSOLIDADA,
                llm_used=llm_provider,
            )

            return post_id
        else:
            logger.error(
                "Falha ao publicar consolidada (HTTP %d): %s — %s",
                resp.status_code, title[:60], resp.text[:300],
            )

    except Exception as e:
        logger.error("Erro ao publicar consolidada: %s", e)

    return None
