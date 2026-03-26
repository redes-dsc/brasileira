"""Coletor scraper com estratégia HTTP/Playwright."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

DEFAULT_HTTP_TIMEOUT = 20.0
DEFAULT_PLAYWRIGHT_TIMEOUT_MS = 45000


class ScraperEngine:
    """Extrai artigos de fontes scraper estáticas ou JS-heavy."""

    def __init__(self):
        self._http: Optional[httpx.AsyncClient] = None
        self._playwright = None
        self._browser = None

    async def start(self) -> None:
        """Inicializa recursos de scraping."""

        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(DEFAULT_HTTP_TIMEOUT),
                limits=httpx.Limits(max_connections=60, max_keepalive_connections=30),
                follow_redirects=True,
                headers={"User-Agent": "BrasileiraNewsBot/3.0"},
            )

    async def stop(self) -> None:
        """Libera recursos de HTTP e Playwright."""

        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
        if self._http is not None and not self._http.is_closed:
            await self._http.aclose()

    async def _ensure_browser(self):
        if self._playwright is None:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
        if self._browser is None:
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )

    def _extract_with_soup(self, html: str, base_url: str, selectors: list[str], limit: int = 200) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        links: list[dict] = []
        seen: set[str] = set()
        for selector in selectors:
            for node in soup.select(selector):
                href = node.get("href")
                title = (node.get_text(" ", strip=True) or "").strip()
                if not href or not title:
                    continue
                absolute_url = urljoin(base_url, href)
                if absolute_url in seen:
                    continue
                seen.add(absolute_url)
                links.append({"titulo": title, "url": absolute_url})
                if len(links) >= limit:
                    return links
        return links

    async def collect(self, source_config: dict) -> list[dict]:
        """Coleta artigos de fonte scraper."""

        if self._http is None or self._http.is_closed:
            await self.start()

        base_url = source_config["url"]
        fonte_id = source_config["fonte_id"]
        fonte_nome = source_config.get("nome", "desconhecido")
        config = source_config.get("config_scraper") or {}
        selectors = config.get("selectors") or ["a[href]"]
        needs_js = bool(config.get("needs_javascript", False))

        html: str
        if needs_js:
            await self._ensure_browser()
            context = await self._browser.new_context()
            page = await context.new_page()
            try:
                await page.goto(base_url, wait_until="domcontentloaded", timeout=DEFAULT_PLAYWRIGHT_TIMEOUT_MS)
                html = await page.content()
            finally:
                await page.close()
                await context.close()
        else:
            response = await self._http.get(base_url)
            response.raise_for_status()
            html = response.text

        extracted = self._extract_with_soup(html, base_url, selectors)
        now = datetime.now(timezone.utc).isoformat()
        group = config.get("grupo", "geral")

        articles: list[dict] = []
        for item in extracted:
            url = item["url"]
            title = item["titulo"]
            url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
            articles.append(
                {
                    "titulo": title,
                    "url": url,
                    "url_hash": url_hash,
                    "data_publicacao": None,
                    "resumo": "",
                    "og_image": None,
                    "fonte_id": fonte_id,
                    "fonte_nome": fonte_nome,
                    "grupo": group,
                    "tipo_coleta": "scraper",
                    "coletado_em": now,
                    "near_duplicate": False,
                    "near_duplicate_of": None,
                }
            )
        return articles
