
"""

Extração de conteúdo completo de artigos para o Motor Scrapers (Raia 2).

Usa newspaper3k como extrator primário com fallback para BeautifulSoup.

"""



import logging

import re

from urllib.parse import urljoin, urlparse



import chardet

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

    "DNT": "1",

}



_TIMEOUT = 30

_MIN_PALAVRAS = 150





def _fetch_html(url: str) -> tuple[str, str]:

    try:

        resp = requests.get(url, headers=_DEFAULT_HEADERS, timeout=_TIMEOUT, allow_redirects=True)

        resp.raise_for_status()

        raw = resp.content

        detected = chardet.detect(raw)

        encoding = detected.get("encoding", "utf-8") or "utf-8"

        html = raw.decode(encoding, errors="replace")

        return html, html

    except Exception as e:

        logger.warning("Erro ao buscar %s: %s | Tipo: %s", url[:80], e, type(e).__name__)

        return "", ""





def _extrair_via_newspaper(url: str, html: str) -> dict | None:

    try:
        from newspaper import Article
        article = Article(url, language="pt")
        article.download(input_html=html)
        article.parse()

        titulo = article.title or ""
        texto = article.text or ""
        autores = article.authors or []
        data = article.publish_date
        imagem = article.top_image or ""

        if len(texto.split()) < _MIN_PALAVRAS:
            return None
        return {
            "titulo": titulo,
            "conteudo": texto[:15000],
            "autor": ", ".join(autores) if autores else "",
            "data": str(data) if data else "",
            "imagem": imagem,
            "metodo": "newspaper3k",
        }

    except Exception as e:
        logger.debug("newspaper3k falhou para %s: %s", url[:80], e)
        return None
    finally:
        if 'article' in locals():
            del article





def _extrair_via_bs4(url: str, html: str) -> dict | None:

    try:

        soup = BeautifulSoup(html, "html.parser")



        for tag in soup.find_all(["script", "style", "nav", "footer", "aside", "iframe", "noscript", "form", "button", "header"]):

            tag.decompose()



        for selector in [

            '[class*="sidebar"]', '[class*="menu"]', '[class*="nav"]',

            '[class*="footer"]', '[class*="header"]', '[class*="ad-"]',

            '[class*="advertisement"]', '[class*="banner"]', '[class*="cookie"]',

            '[class*="modal"]', '[class*="popup"]', '[class*="social"]',

            '[class*="share"]', '[class*="comment"]', '[class*="related"]',

            '[id*="sidebar"]', '[id*="menu"]', '[id*="footer"]',

            '[id*="header"]', '[id*="ad-"]', '[id*="comment"]',

        ]:

            for el in soup.select(selector):

                el.decompose()



        titulo = ""

        for sel in ["h1", "article h1", ".entry-title", ".post-title", ".article-title", ".titulo-noticia"]:

            el = soup.select_one(sel)

            if el:

                titulo = el.get_text(strip=True)

                break

        if not titulo:

            title_tag = soup.find("title")

            if title_tag:

                titulo = title_tag.get_text(strip=True)



        texto = ""

        for selector in [

            "article", '[class*="article-body"]', '[class*="article-content"]',

            '[class*="post-content"]', '[class*="entry-content"]',

            '[class*="materia-conteudo"]', '[class*="content-text"]',

            '[class*="texto"]', '[class*="noticia-conteudo"]',

            '[itemprop="articleBody"]', "main", ".content", "#content",

        ]:

            element = soup.select_one(selector)

            if element:

                texto = element.get_text(separator="\n", strip=True)

                if len(texto.split()) >= _MIN_PALAVRAS:

                    break

                texto = ""



        if not texto:

            body = soup.find("body")

            if body:

                texto = body.get_text(separator="\n", strip=True)



        if len(texto.split()) < _MIN_PALAVRAS:

            return None



        autor = ""

        for sel in ['[class*="author"]', '[class*="autor"]', '[rel="author"]', '[itemprop="author"]', '.byline']:

            el = soup.select_one(sel)

            if el:

                autor = el.get_text(strip=True)

                break



        data = ""

        for sel in ['time[datetime]', '[class*="date"]', '[class*="data"]', '[itemprop="datePublished"]', ".published"]:

            el = soup.select_one(sel)

            if el:

                data = el.get("datetime", "") or el.get_text(strip=True)

                break



        imagem = ""

        og_img = soup.find("meta", property="og:image")

        if og_img:

            imagem = og_img.get("content", "")

        if not imagem:

            for sel in ["article img", "figure img", ".post-thumbnail img", '[class*="featured"] img', "main img"]:

                el = soup.select_one(sel)

                if el:

                    src = el.get("src", "") or el.get("data-src", "")

                    if src and not any(p in src.lower() for p in ["logo", "icon", "avatar"]):

                        imagem = urljoin(url, src)

                        break



        linhas = [l.strip() for l in texto.split("\n") if l.strip()]

        texto = "\n\n".join(linhas)



        return {

            "titulo": titulo,

            "conteudo": texto[:10000],

            "autor": autor,

            "data": data,

            "imagem": imagem,

            "metodo": "beautifulsoup",

        }

    except Exception as e:

        logger.warning("BS4 falhou para %s: %s", url[:80], e)

        return None





def _extrair_via_jina(url: str) -> dict | None:

    try:

        jina_url = f"https://r.jina.ai/{url}"

        headers = {

            "User-Agent": _DEFAULT_HEADERS["User-Agent"],

            "Accept": "text/html"

        }

        res = requests.get(jina_url, headers=headers, timeout=_TIMEOUT)

        res.raise_for_status()

        

        texto = res.text

        if "Markdown Content:" in texto:

            texto = texto.split("Markdown Content:", 1)[1].strip()

            

        if len(texto.split()) < _MIN_PALAVRAS:

            return None

            

        return {

            "titulo": "", 

            "conteudo": texto[:15000],

            "autor": "",

            "data": "",

            "imagem": "",

            "metodo": "jina_reader",

        }

    except Exception as e:

        logger.warning("Jina Reader falhou para %s: %s", url[:80], e)

        return None





def extrair_conteudo_completo(url: str) -> dict | None:

    """

    Extrai conteúdo completo de um artigo.

    Usa newspaper3k como extrator primário, BS4 como fallback.

    """

    html, html_raw = _fetch_html(url)

    if not html:

        return None



    resultado = _extrair_via_newspaper(url, html)

    if resultado:

        logger.info("Conteúdo extraído via newspaper3k (%d palavras): %s", len(resultado["conteudo"].split()), url[:80])

        return resultado



    resultado = _extrair_via_bs4(url, html)

    if resultado:

        logger.info("[FALLBACK] Conteúdo extraído via BS4 (%d palavras): %s", len(resultado["conteudo"].split()), url[:80])

        return resultado



    resultado = _extrair_via_jina(url)

    if resultado:

        logger.info("[FALLBACK 2] Conteúdo extraído via Jina Reader (%d palavras): %s", len(resultado["conteudo"].split()), url[:80])

        return resultado



    logger.warning("Não foi possível extrair conteúdo de %s", url[:80])

    return None





def extrair_html_bruto(url: str) -> str:

    """Retorna HTML bruto da página (para extração de imagens via image_handler)."""

    html, _ = _fetch_html(url)

    return html


def extrair_texto_completo(url: str) -> str:
    """Alias de compatibilidade — retorna apenas o texto extraído (string).

    Usado por scripts legados que importavam do antigo extrator_conteudo.py da raiz.
    """
    result = extrair_conteudo_completo(url)
    if result and result.get("text"):
        return result["text"][:25000]
    return ""
