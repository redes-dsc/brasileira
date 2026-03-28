"""Tier 2: Busca em bancos de imagens (Pexels, Unsplash)."""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class Tier2StockSearch:
    """Busca imagens em bancos de stock gratuitos."""

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self.pexels_key = os.getenv("PEXELS_API_KEY", "")
        self.unsplash_key = os.getenv("UNSPLASH_API_KEY", "")

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=15.0, http2=True)
        return self._client

    async def search(self, query: str, editoria: str = "") -> dict[str, Any]:
        """Busca imagem em Pexels -> Unsplash -> fallback."""
        # Pexels
        if self.pexels_key:
            result = await self._search_pexels(query)
            if result:
                return {"success": True, "url": result["url"], "source": "pexels",
                        "attribution": result.get("attribution", ""), "tier": 2}

        # Unsplash
        if self.unsplash_key:
            result = await self._search_unsplash(query)
            if result:
                return {"success": True, "url": result["url"], "source": "unsplash",
                        "attribution": result.get("attribution", ""), "tier": 2}

        return {"success": False, "reason": "nenhuma imagem stock encontrada"}

    async def _search_pexels(self, query: str) -> Optional[dict[str, str]]:
        try:
            client = await self._get_client()
            response = await client.get(
                "https://api.pexels.com/v1/search",
                params={"query": query, "per_page": 3, "locale": "pt-BR"},
                headers={"Authorization": self.pexels_key},
            )
            response.raise_for_status()
            data = response.json()
            photos = data.get("photos", [])
            if photos:
                photo = photos[0]
                return {
                    "url": photo["src"]["large2x"],
                    "attribution": f"Foto por {photo.get('photographer', 'Pexels')} via Pexels",
                }
        except Exception:
            logger.debug("Pexels search falhou para '%s'", query, exc_info=True)
        return None

    async def _search_unsplash(self, query: str) -> Optional[dict[str, str]]:
        try:
            client = await self._get_client()
            response = await client.get(
                "https://api.unsplash.com/search/photos",
                params={"query": query, "per_page": 3},
                headers={"Authorization": f"Client-ID {self.unsplash_key}"},
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            if results:
                photo = results[0]
                return {
                    "url": photo["urls"]["regular"],
                    "attribution": f"Foto por {photo.get('user', {}).get('name', 'Unsplash')} via Unsplash",
                }
        except Exception:
            logger.debug("Unsplash search falhou para '%s'", query, exc_info=True)
        return None

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
