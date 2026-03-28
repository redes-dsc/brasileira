"""Extração de conteúdo de artigos com pipeline de fallback."""

from __future__ import annotations

import asyncio
import json
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


async def _fetch_html(url: str) -> Optional[str]:
    try:
        client = await _get_client()
        response = await client.get(url)
        response.raise_for_status()
        return response.text
    except Exception:
        logger.warning("Falha ao buscar HTML de %s", url[:100], exc_info=True)
        return None


def _extraction_to_reporter_dict(
    extracted: dict[str, Any], metodo: str, html: str, og_image: Optional[str]
) -> dict[str, Any]:
    authors = extracted.get("authors") or []
    autor = authors[0] if authors else None
    out: dict[str, Any] = {
        "conteudo": extracted.get("text", ""),
        "conteudo_html": html,
        "og_image": og_image,
        "autor": autor,
        "metodo": metodo,
    }
    return out


async def extract_content(
    url: str, resumo: str = "", og_image: Optional[str] = None
) -> dict[str, Any]:
    """Extrai conteúdo limpo de um artigo.

    Pipeline: trafilatura → newspaper4k → BeautifulSoup (seletivo).

    Retorna dict compatível com o reporter: conteudo, conteudo_html, og_image, autor, metodo.
    """
    base_og = og_image
    html: Optional[str] = await _fetch_html(url)

    fallback: dict[str, Any] = {
        "conteudo": "",
        "conteudo_html": "",
        "og_image": base_og,
        "autor": None,
        "metodo": "resumo_fallback",
    }

    if not html:
        fallback["conteudo"] = resumo
        return fallback

    if not base_og:
        base_og = _extract_og_image(html)

    # Tier 1: trafilatura (melhor extrator geral)
    extracted = _try_trafilatura(url, html)
    if extracted and len(extracted.get("text", "")) > 200:
        logger.debug("Extração via trafilatura: %d chars", len(extracted["text"]))
        r = _extraction_to_reporter_dict(extracted, "trafilatura", html, base_og)
        return r

    # Tier 2: newspaper4k
    extracted = await _try_newspaper(url)
    if extracted and len(extracted.get("text", "")) > 200:
        logger.debug("Extração via newspaper4k: %d chars", len(extracted["text"]))
        return _extraction_to_reporter_dict(extracted, "newspaper4k", html, base_og)

    # Tier 3: BeautifulSoup seletivo
    extracted = _try_beautifulsoup(html)
    if extracted and len(extracted.get("text", "")) > 100:
        logger.debug("Extração via BeautifulSoup: %d chars", len(extracted["text"]))
        return _extraction_to_reporter_dict(extracted, "beautifulsoup", html, base_og)

    logger.warning("Extração falhou para %s; usando resumo", url)
    fallback["conteudo"] = resumo
    fallback["conteudo_html"] = html
    fallback["og_image"] = base_og
    return fallback


def _try_trafilatura(url: str, html: Optional[str] = None) -> Optional[dict[str, Any]]:
    try:
        import trafilatura

        if html is None:
            downloaded = trafilatura.fetch_url(url)
        else:
            downloaded = html

        if not downloaded:
            return None

        text = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=True,
            favor_precision=True,
            deduplicate=True,
        )

        metadata = trafilatura.extract(
            downloaded,
            output_format="json",
            include_comments=False,
        )

        if text:
            meta = json.loads(metadata) if metadata else {}
            author = meta.get("author")
            authors_list: list[str] = []
            if author:
                if isinstance(author, list):
                    authors_list = [str(a) for a in author]
                else:
                    authors_list = [str(author)]
            return {
                "title": meta.get("title", ""),
                "text": text,
                "authors": authors_list,
                "publish_date": meta.get("date"),
            }
    except Exception as e:
        logger.debug("trafilatura falhou: %s", e)
    return None


async def _try_newspaper(url: str) -> Optional[dict[str, Any]]:
    def _sync() -> Optional[dict[str, Any]]:
        try:
            from newspaper import Article

            article = Article(url, language="pt")
            article.download()
            article.parse()

            if article.text:
                return {
                    "title": article.title or "",
                    "text": article.text,
                    "authors": list(article.authors) if article.authors else [],
                    "publish_date": str(article.publish_date) if article.publish_date else None,
                }
        except Exception as e:
            logger.debug("newspaper4k falhou: %s", e)
        return None

    return await asyncio.to_thread(_sync)


def _try_beautifulsoup(html: str) -> Optional[dict[str, Any]]:
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        for tag in soup.find_all(
            [
                "nav",
                "header",
                "footer",
                "aside",
                "script",
                "style",
                "iframe",
                "noscript",
                "form",
                "button",
                "input",
                "select",
            ]
        ):
            tag.decompose()

        content = None
        for selector in [
            "article",
            "main",
            ".post-content",
            ".entry-content",
            ".article-body",
            ".story-body",
            "#content",
            ".content",
        ]:
            content = soup.select_one(selector)
            if content:
                break

        if content is None:
            content = soup.body or soup

        paragraphs = content.find_all("p")
        text = "\n\n".join(
            p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 30
        )

        title_tag = soup.find("h1") or soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""

        if text:
            return {
                "title": title,
                "text": text,
                "authors": [],
                "publish_date": None,
            }
    except Exception as e:
        logger.debug("BeautifulSoup falhou: %s", e)
    return None


def _extract_og_image(html: str) -> Optional[str]:
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        tag = soup.find("meta", property="og:image")
        if tag and tag.get("content"):
            return tag["content"]
        tag = soup.find("meta", attrs={"name": "twitter:image"})
        if tag and tag.get("content"):
            return tag["content"]
    except Exception:
        pass
    return None
