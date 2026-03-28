"""Scanner resiliente de portais concorrentes."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from .config import MonitorConcorrenciaConfig
from .schemas import PortalArticle

logger = logging.getLogger(__name__)


class PortalScanner:
    """Coleta manchetes com estratégia browser-first e fallback HTTP."""

    def __init__(self, config: MonitorConcorrenciaConfig):
        self.config = config

    async def _scan_with_playwright(
        self, portal_name: str, portal_url: str, selectors: list[str]
    ) -> list[PortalArticle]:
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
        from playwright.async_api import async_playwright

        items: list[PortalArticle] = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(ignore_https_errors=True)
                page = await context.new_page()
                page.set_default_timeout(self.config.timeout_seconds * 1000)
                await page.goto(portal_url, wait_until="domcontentloaded")
                for selector in selectors:
                    links = await page.query_selector_all(selector)
                    for idx, link in enumerate(links[: self.config.max_articles_per_portal]):
                        text = (await link.inner_text()).strip()
                        href = await link.get_attribute("href")
                        if not text or len(text) < 20:
                            continue
                        if href and href.startswith("/"):
                            href = portal_url.rstrip("/") + href
                        items.append(
                            PortalArticle(
                                portal=portal_name,
                                titulo=text,
                                url=href or portal_url,
                                coletado_em=datetime.now(timezone.utc),
                            )
                        )
                    if items:
                        break
                # dedup por URL/título mantendo ordem
                seen: set[str] = set()
                deduped: list[PortalArticle] = []
                for article in items:
                    key = f"{article.url}|{article.titulo.lower().strip()}"
                    if key in seen:
                        continue
                    seen.add(key)
                    deduped.append(article)
                return deduped[: self.config.max_articles_per_portal]
            except PlaywrightTimeoutError:
                logger.warning("Timeout Playwright em portal=%s", portal_name)
                return []
            finally:
                await browser.close()

    async def _scan_with_httpx(
        self, portal_name: str, portal_url: str, selectors: list[str]
    ) -> list[PortalArticle]:
        for attempt in range(self.config.retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.config.timeout_seconds, follow_redirects=True) as client:
                    response = await client.get(portal_url)
                    response.raise_for_status()
                    soup = BeautifulSoup(response.text, "lxml")
                    items: list[PortalArticle] = []
                    for selector in selectors + ["h1 a", "h2 a", "h3 a", "a"]:
                        for tag in soup.select(selector)[: self.config.max_articles_per_portal]:
                            title = (tag.get_text() or "").strip()
                            href = tag.get("href") if hasattr(tag, "get") else None
                            if not title or len(title) < 20:
                                continue
                            if href and href.startswith("/"):
                                href = portal_url.rstrip("/") + href
                            items.append(
                                PortalArticle(
                                    portal=portal_name,
                                    titulo=title,
                                    url=href or portal_url,
                                    coletado_em=datetime.now(timezone.utc),
                                )
                            )
                        if items:
                            break
                    return items
            except Exception:
                logger.exception("Falha no scan portal=%s attempt=%d", portal_name, attempt)
                if attempt < self.config.retries:
                    await asyncio.sleep(2 ** attempt)
        return []

    async def scan_portal(
        self,
        portal_name: str,
        portal_url: str,
        requires_browser: bool = False,
        selectors: list[str] | None = None,
    ) -> list[PortalArticle]:
        selectors = selectors or []
        if requires_browser:
            try:
                data = await self._scan_with_playwright(portal_name, portal_url, selectors)
                if data:
                    return data
                logger.info("Playwright sem dados em %s; acionando fallback HTTP", portal_name)
            except Exception:
                logger.exception("Falha Playwright em %s; acionando fallback HTTP", portal_name)
        return await self._scan_with_httpx(portal_name, portal_url, selectors)
