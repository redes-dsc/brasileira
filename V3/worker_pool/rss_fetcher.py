"""Coletor RSS assíncrono com ETag/If-Modified-Since."""

from __future__ import annotations

import calendar
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
import feedparser
import httpx

logger = logging.getLogger(__name__)

FEED_FETCH_TIMEOUT = 12.0
DEFAULT_CUTOFF_HOURS = 48
USER_AGENT = "BrasileiraNewsBot/3.0 (+https://brasileira.news/bot)"


class RSSFetcher:
    """Processa feeds RSS/Atom com HTTPX e feedparser."""

    def __init__(self, redis_client=None):
        self.redis = redis_client
        self._http: Optional[httpx.AsyncClient] = None

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(FEED_FETCH_TIMEOUT),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=50),
                follow_redirects=True,
                http2=True,
                headers={"User-Agent": USER_AGENT},
            )
        return self._http

    async def close(self) -> None:
        if self._http is not None and not self._http.is_closed:
            await self._http.aclose()

    async def _get_conditional_headers(self, fonte_id: int) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.redis is None:
            return headers
        etag = await self.redis.get(f"source:etag:{fonte_id}")
        last_modified = await self.redis.get(f"source:last_modified:{fonte_id}")
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        return headers

    async def _persist_cache_headers(self, fonte_id: int, response: httpx.Response) -> None:
        if self.redis is None:
            return
        etag = response.headers.get("ETag")
        last_modified = response.headers.get("Last-Modified")
        if etag:
            await self.redis.set(f"source:etag:{fonte_id}", etag, ex=86400)
        if last_modified:
            await self.redis.set(f"source:last_modified:{fonte_id}", last_modified, ex=86400)

    @staticmethod
    def _entry_link(entry: dict) -> str:
        link = (entry.get("link") or "").strip()
        if link:
            return link
        for item in entry.get("links") or []:
            if not isinstance(item, dict):
                continue
            href = (item.get("href") or "").strip()
            if not href:
                continue
            rel = (item.get("rel") or "alternate").lower()
            if rel in ("alternate", "self", ""):
                return href
        return ""

    @staticmethod
    def _parse_published(entry: dict) -> Optional[datetime]:
        candidates = [entry.get("published"), entry.get("updated")]
        for value in candidates:
            if not value:
                continue
            try:
                dt = parsedate_to_datetime(value)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue
        for key in ("published_parsed", "updated_parsed"):
            struct = entry.get(key)
            if struct is None:
                continue
            try:
                ts = calendar.timegm(struct)
                return datetime.fromtimestamp(ts, tz=timezone.utc)
            except (TypeError, ValueError, OverflowError):
                continue
        return None

    async def collect(
        self,
        feed_url: str,
        fonte_id: int,
        fonte_nome: str,
        grupo: str = "geral",
        cutoff_hours: int = DEFAULT_CUTOFF_HOURS,
    ) -> list[dict]:
        """Coleta artigos novos de um feed RSS/Atom."""

        client = await self._client()
        headers = await self._get_conditional_headers(fonte_id)
        response = await client.get(feed_url, headers=headers)

        if response.status_code == 304:
            logger.debug("Feed não modificado (304): fonte_id=%s", fonte_id)
            return []

        response.raise_for_status()
        await self._persist_cache_headers(fonte_id, response)

        parsed = feedparser.parse(response.text)
        entries = getattr(parsed, "entries", [])

        cutoff = datetime.now(timezone.utc) - timedelta(hours=cutoff_hours)
        collected: list[dict] = []

        for entry in entries:
            title = (entry.get("title") or "").strip()
            link = self._entry_link(entry).strip()
            if not title or not link:
                continue

            published = self._parse_published(entry)
            if published and published < cutoff:
                continue

            summary = (entry.get("summary") or "").strip()
            og_image = None
            media_content = entry.get("media_content") or []
            if media_content and isinstance(media_content, list):
                first = media_content[0]
                if isinstance(first, dict):
                    og_image = first.get("url")

            url_hash = hashlib.sha256(link.encode("utf-8")).hexdigest()
            collected.append(
                {
                    "titulo": title,
                    "url": link,
                    "url_hash": url_hash,
                    "data_publicacao": published.isoformat() if published else None,
                    "resumo": summary,
                    "og_image": og_image,
                    "fonte_id": fonte_id,
                    "fonte_nome": fonte_nome,
                    "grupo": grupo,
                    "tipo_coleta": "rss",
                    "coletado_em": datetime.now(timezone.utc).isoformat(),
                    "near_duplicate": False,
                    "near_duplicate_of": None,
                }
            )

        return collected
