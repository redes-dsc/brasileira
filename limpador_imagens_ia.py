
# -*- coding: utf-8 -*-
"""
Limpador de imagens IA — substitui capas geradas por DALL-E pelo placeholder padrão.
Executar manualmente quando necessário.

Fixes aplicados (bugs 12.1, 12.2, 12.3):
- obter_id() NÃO roda no import (era efeito colateral perigoso)
- eh_ia() melhorada com mais heurísticas
- Paginação com limite de segurança (max 200 páginas)
"""

import requests
import os
import logging

logger = logging.getLogger("limpador_imagens")

# Carregar config sem efeitos colaterais no import
try:
    from config_geral import WP_URL, AUTH_HEADERS
except ImportError:
    WP_URL = os.getenv("WP_API_BASE", "")
    AUTH_HEADERS = {}

URL_DEFAULT = "https://brasileira.news/wp-content/uploads/sites/7/2026/02/imagem-brasileira.png"

# Heurísticas de detecção de imagem gerada por IA
_IA_MARKERS = [
    "inteligência artificial", "inteligencia artificial",
    "dall-e", "dall·e", "midjourney", "stable diffusion",
    "editorial news photography", "no text", "sem letras",
    "imagem gerada", "ai generated", "a.i. generated",
    "fotorrealista", "representando:",
]


def obter_id_placeholder():
    """Obtém o ID do placeholder padrão no WordPress, criando se necessário."""
    res = requests.get(f"{WP_URL}/media?search=imagem-brasileira", headers=AUTH_HEADERS, timeout=15)
    if res.status_code == 200 and len(res.json()) > 0:
        return res.json()[0]['id']

    # Criar placeholder se não existir
    img_data = requests.get(URL_DEFAULT, timeout=15).content
    upd = requests.post(
        f"{WP_URL}/media",
        headers={
            **AUTH_HEADERS,
            'Content-Disposition': 'attachment; filename="imagem-default.png"',
            'Content-Type': 'image/png'
        },
        data=img_data,
        timeout=30,
    )
    if upd.status_code in (200, 201):
        return upd.json().get('id')
    return None


def eh_ia(m_id):
    """Verifica se uma mídia foi gerada por IA (heurística por metadados)."""
    try:
        res = requests.get(f"{WP_URL}/media/{m_id}", headers=AUTH_HEADERS, timeout=10)
        if res.status_code != 200:
            return False
        m = res.json()
        text = " ".join([
            str(m.get('title', {}).get('rendered', '')),
            str(m.get('caption', {}).get('rendered', '')),
            str(m.get('alt_text', '')),
            str(m.get('source_url', '')),
            str(m.get('description', {}).get('rendered', '')),
        ]).lower()
        return any(marker in text for marker in _IA_MARKERS)
    except Exception as e:
        logger.warning("Erro ao verificar mídia %s: %s", m_id, e)
        return False


def executar(dry_run=False, max_pages=200):
    """Executa a substituição de capas IA pelo placeholder."""
    id_def = obter_id_placeholder()
    if not id_def:
        logger.error("Não foi possível obter/criar placeholder. Abortando.")
        return 0

    pag = 1
    cor = 0

    while pag <= max_pages:
        try:
            resp = requests.get(
                f"{WP_URL}/posts?per_page=50&page={pag}",
                headers=AUTH_HEADERS, timeout=20
            )
            if resp.status_code != 200:
                break
            posts = resp.json()
            if not posts or isinstance(posts, dict):
                break
        except Exception as e:
            logger.error("Erro ao buscar posts (página %d): %s", pag, e)
            break

        for p in posts:
            m_id = p.get('featured_media', 0)
            if m_id != 0 and m_id != id_def and eh_ia(m_id):
                title_short = p.get('title', {}).get('rendered', '')[:40]
                if dry_run:
                    logger.info("[DRY RUN] Trocaria IA: %s", title_short)
                    cor += 1
                else:
                    try:
                        r = requests.post(
                            f"{WP_URL}/posts/{p['id']}",
                            json={"featured_media": id_def},
                            headers=AUTH_HEADERS, timeout=15
                        )
                        if r.status_code == 200:
                            cor += 1
                            logger.info("Trocando IA: %s", title_short)
                    except Exception as e:
                        logger.warning("Erro ao trocar imagem de post %s: %s", p.get('id'), e)

        pag += 1

    logger.info("Feito! %d capas %s.", cor, "seriam substituídas" if dry_run else "substituídas")
    return cor


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    dry = "--dry-run" in sys.argv
    executar(dry_run=dry)
