
"""

Detecção automática de estratégia de scraping por site.

Estratégias: A (HTML estático), B (JSON embarcado/Next.js),

C (API JSON pública), D (feed não-padrão), E (sitemap XML).

"""



import json

import logging

import re

from urllib.parse import urljoin, urlparse



import chardet

import feedparser

import requests

from bs4 import BeautifulSoup



logger = logging.getLogger("motor_scrapers")



_DEFAULT_HEADERS = {

    "User-Agent": (

        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "

        "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"

    ),

    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",

    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",

    "Accept-Encoding": "gzip, deflate",

}



_TIMEOUT = 30





def _fetch_raw(url: str) -> tuple[str, int]:

    try:

        resp = requests.get(url, headers=_DEFAULT_HEADERS, timeout=_TIMEOUT)

        if resp.status_code != 200:

            return "", resp.status_code

        raw = resp.content

        detected = chardet.detect(raw)

        encoding = detected.get("encoding", "utf-8") or "utf-8"

        return raw.decode(encoding, errors="replace"), resp.status_code

    except Exception as e:

        logger.debug("Erro ao buscar %s: %s", url[:80], e)

        return "", 0





def detectar_next_data(html: str) -> dict | None:

    """Detecta e extrai __NEXT_DATA__ de páginas Next.js."""

    match = re.search(

        r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>',

        html,

        re.DOTALL,

    )

    if not match:

        return None

    try:

        data = json.loads(match.group(1))

        return data

    except json.JSONDecodeError:

        return None





def detectar_feed_nao_padrao(url_home: str) -> str | None:

    """Tenta encontrar feed RSS/Atom não-padrão no site."""

    sufixos = ["/feed", "/feed/", "/rss", "/rss/", "/rss.xml", "/atom.xml", "/feed.xml", "/index.xml"]

    for sufixo in sufixos:

        feed_url = urljoin(url_home, sufixo)

        try:

            resp = requests.get(feed_url, headers=_DEFAULT_HEADERS, timeout=15, allow_redirects=True)

            if resp.status_code == 200:

                ct = resp.headers.get("Content-Type", "")

                if any(t in ct for t in ("xml", "rss", "atom", "feed")):

                    parsed = feedparser.parse(resp.text)

                    if parsed.entries:

                        logger.info("Feed não-padrão encontrado: %s (%d entradas)", feed_url, len(parsed.entries))

                        return feed_url

        except Exception:

            continue

    return None





def detectar_sitemap(url_home: str) -> str | None:

    """Tenta encontrar sitemap de notícias."""

    candidatos = ["/sitemap.xml", "/sitemap_news.xml", "/news-sitemap.xml", "/sitemap-news.xml", "/sitemap_index.xml"]

    for path in candidatos:

        sitemap_url = urljoin(url_home, path)

        try:

            resp = requests.get(sitemap_url, headers=_DEFAULT_HEADERS, timeout=15)

            if resp.status_code == 200 and "<url>" in resp.text.lower():

                logger.info("Sitemap encontrado: %s", sitemap_url)

                return sitemap_url

        except Exception:

            continue

    return None





def detectar_api_json(url_home: str) -> str | None:

    """Tenta encontrar API JSON pública no site."""

    candidatos = ["/api/noticias", "/api/news", "/api/v1/news", "/wp-json/wp/v2/posts", "/api/posts"]

    for path in candidatos:

        api_url = urljoin(url_home, path)

        try:

            resp = requests.get(api_url, headers={**_DEFAULT_HEADERS, "Accept": "application/json"}, timeout=15)

            if resp.status_code == 200:

                ct = resp.headers.get("Content-Type", "")

                if "json" in ct:

                    data = resp.json()

                    if isinstance(data, (list, dict)):

                        logger.info("API JSON encontrada: %s", api_url)

                        return api_url

        except Exception:

            continue

    return None





def detectar_estrategia(fonte: dict) -> tuple[str, dict]:

    """

    Detecta a melhor estratégia de scraping para uma fonte.

    Retorna (estrategia, metadata) onde estrategia é A|B|C|D|E.

    """

    estrategia_config = fonte.get("estrategia", "").upper()

    url_home = fonte.get("url_home", "")

    url_noticias = fonte.get("url_noticias", "")

    nome = fonte.get("nome", "desconhecido")



    if estrategia_config in ("A", "B", "C", "D", "E"):

        logger.debug("Usando estratégia configurada %s para %s", estrategia_config, nome)

        return estrategia_config, {}



    logger.info("Detectando estratégia para %s (%s)...", nome, url_noticias or url_home)



    url_alvo = url_noticias or url_home

    if not url_alvo:

        logger.warning("Fonte %s sem URL. Usando estratégia A (padrão).", nome)

        return "A", {}



    html, status = _fetch_raw(url_alvo)

    if not html:

        logger.warning("Não foi possível acessar %s (status=%d). Usando estratégia A.", nome, status)

        return "A", {}



    next_data = detectar_next_data(html)

    if next_data:

        logger.info("Estratégia B detectada para %s (Next.js).", nome)

        return "B", {"next_data": next_data}



    feed_url = detectar_feed_nao_padrao(url_home)

    if feed_url:

        logger.info("Estratégia D detectada para %s (feed: %s).", nome, feed_url)

        return "D", {"url_feed": feed_url}



    api_url = detectar_api_json(url_home)

    if api_url:

        logger.info("Estratégia C detectada para %s (API: %s).", nome, api_url)

        return "C", {"url_api": api_url}



    sitemap_url = detectar_sitemap(url_home)

    if sitemap_url:

        logger.info("Estratégia E detectada para %s (sitemap: %s).", nome, sitemap_url)

        return "E", {"url_sitemap": sitemap_url}



    logger.info("Estratégia A (HTML estático) para %s (fallback).", nome)

    return "A", {}

