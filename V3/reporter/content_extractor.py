"""Extração de conteúdo com cascade: trafilatura -> BS4 article -> BS4 full -> resumo."""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

_HTTP_CLIENT: Optional[httpx.AsyncClient] = None


async def _get_client() -> httpx.AsyncClient:
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None or _HTTP_CLIENT.is_closed:
        _HTTP_CLIENT = httpx.AsyncClient(
            timeout=20.0,
            http2=True,
            headers={"User-Agent": "BrasileiraNewsBot/3.0"},
            follow_redirects=True,
        )
    return _HTTP_CLIENT


async def extract_content(url: str, resumo: str = "", og_image: Optional[str] = None) -> dict[str, Any]:
    """Extrai conteúdo limpo de uma URL com cascade de métodos."""
    result = {
        "conteudo": "",
        "conteudo_html": "",
        "og_image": og_image,
        "autor": None,
        "metodo": "resumo_fallback",
    }

    html = await _fetch_html(url)
    if not html:
        result["conteudo"] = resumo
        return result

    # Tier 1: trafilatura (melhor para artigos de notícias)
    conteudo = _extract_trafilatura(html)
    if conteudo and len(conteudo) > 200:
        result["conteudo"] = conteudo
        result["conteudo_html"] = html
        result["metodo"] = "trafilatura"
        if not result["og_image"]:
            result["og_image"] = _extract_og_image(html)
        return result

    # Tier 2: BeautifulSoup article tag
    conteudo = _extract_article_tag(html)
    if conteudo and len(conteudo) > 150:
        result["conteudo"] = conteudo
        result["conteudo_html"] = html
        result["metodo"] = "bs4_article"
        if not result["og_image"]:
            result["og_image"] = _extract_og_image(html)
        return result

    # Tier 3: BeautifulSoup paragraphs
    conteudo = _extract_paragraphs(html)
    if conteudo and len(conteudo) > 100:
        result["conteudo"] = conteudo
        result["conteudo_html"] = html
        result["metodo"] = "bs4_paragraphs"
        if not result["og_image"]:
            result["og_image"] = _extract_og_image(html)
        return result

    # Tier 4: resumo original
    result["conteudo"] = resumo
    result["conteudo_html"] = html
    return result


async def _fetch_html(url: str) -> Optional[str]:
    """Busca HTML da URL com retry."""
    try:
        client = await _get_client()
        response = await client.get(url)
        response.raise_for_status()
        return response.text
    except Exception:
        logger.warning("Falha ao buscar HTML de %s", url[:100], exc_info=True)
        return None


def _extract_trafilatura(html: str) -> Optional[str]:
    """Extração via trafilatura - melhor para artigos de notícias."""
    try:
        import trafilatura
        result = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
            favor_precision=True,
        )
        return result
    except Exception:
        logger.debug("trafilatura falhou", exc_info=True)
        return None


def _extract_article_tag(html: str) -> Optional[str]:
    """Extrai texto de tags <article> ou role=main."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        article = soup.find("article") or soup.find(attrs={"role": "main"}) or soup.find(class_=lambda c: c and "article" in str(c).lower())
        if article:
            paragraphs = article.find_all("p")
            text = "\n\n".join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20)
            return text
    except Exception:
        logger.debug("BS4 article extraction falhou", exc_info=True)
    return None


def _extract_paragraphs(html: str) -> Optional[str]:
    """Extrai todos os <p> com filtro de tamanho."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        # Remove nav, footer, aside, script, style
        for tag in soup.find_all(["nav", "footer", "aside", "script", "style", "header"]):
            tag.decompose()
        paragraphs = soup.find_all("p")
        texts = [p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 30]
        return "\n\n".join(texts)
    except Exception:
        logger.debug("BS4 paragraph extraction falhou", exc_info=True)
    return None


def _extract_og_image(html: str) -> Optional[str]:
    """Extrai og:image do HTML."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        # og:image
        tag = soup.find("meta", property="og:image")
        if tag and tag.get("content"):
            return tag["content"]
        # twitter:image
        tag = soup.find("meta", attrs={"name": "twitter:image"})
        if tag and tag.get("content"):
            return tag["content"]
    except Exception:
        pass
    return None
