"""Tier 2: Busca de imagens em bancos de stock (Pexels + Unsplash)."""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", os.getenv("UNSPLASH_API_KEY", ""))


class Tier2StockSearch:
    """Busca imagens em bancos de stock gratuitos (Pexels + Unsplash)."""

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self.pexels_key = PEXELS_API_KEY
        self.unsplash_key = UNSPLASH_ACCESS_KEY

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=15.0, http2=True)
        return self._client

    async def search(self, query: str, editoria: str = "", min_width: int = 800) -> dict[str, Any]:
        """Busca imagem em Pexels -> Unsplash -> fallback.
        
        Args:
            query: Termo de busca para a imagem
            editoria: Editoria do artigo (para contexto)
            min_width: Largura mínima da imagem (default: 800)
            
        Returns:
            dict com: success, url, source, attribution, tier, alt, 
                     download_url, source_url, photographer, width, height
        """
        # Tentar Pexels primeiro (melhor qualidade editorial)
        if self.pexels_key:
            result = await self._search_pexels(query, min_width)
            if result:
                return {
                    "success": True,
                    "url": result["url"],
                    "source": "pexels",
                    "attribution": f"Foto por {result.get('photographer', 'Pexels')} via Pexels",
                    "tier": 2,
                    "alt": result.get("alt_text", query),
                    "download_url": result.get("download_url"),
                    "source_url": result.get("source_url"),
                    "photographer": result.get("photographer"),
                    "width": result.get("width"),
                    "height": result.get("height"),
                }

        # Fallback: Unsplash
        if self.unsplash_key:
            result = await self._search_unsplash(query, min_width)
            if result:
                return {
                    "success": True,
                    "url": result["url"],
                    "source": "unsplash",
                    "attribution": f"Foto por {result.get('photographer', 'Unsplash')} via Unsplash",
                    "tier": 2,
                    "alt": result.get("alt_text", query),
                    "download_url": result.get("download_url"),
                    "source_url": result.get("source_url"),
                    "photographer": result.get("photographer"),
                    "width": result.get("width"),
                    "height": result.get("height"),
                }

        logger.warning("Tier 2 falhou para query '%s' (sem API keys ou sem resultados)", query)
        return {"success": False, "reason": "nenhuma imagem stock encontrada"}

    async def _search_pexels(self, query: str, min_width: int) -> Optional[dict]:
        """Busca no Pexels API."""
        try:
            client = await self._get_client()
            response = await client.get(
                "https://api.pexels.com/v1/search",
                params={
                    "query": query,
                    "per_page": 5,
                    "locale": "pt-BR",
                    "size": "large"
                },
                headers={"Authorization": self.pexels_key},
            )
            response.raise_for_status()
            data = response.json()

            for photo in data.get("photos", []):
                if photo.get("width", 0) >= min_width:
                    return {
                        "url": photo["src"]["large2x"],
                        "download_url": photo["src"]["original"],
                        "source": "pexels",
                        "source_url": photo["url"],
                        "photographer": photo.get("photographer", ""),
                        "alt_text": photo.get("alt", query),
                        "width": photo.get("width"),
                        "height": photo.get("height"),
                    }
        except Exception as e:
            logger.debug("Pexels search falhou: %s", e)
        return None

    async def _search_unsplash(self, query: str, min_width: int) -> Optional[dict]:
        """Busca no Unsplash API."""
        try:
            client = await self._get_client()
            response = await client.get(
                "https://api.unsplash.com/search/photos",
                params={
                    "query": query,
                    "per_page": 5,
                    "content_filter": "high"
                },
                headers={"Authorization": f"Client-ID {self.unsplash_key}"},
            )
            response.raise_for_status()
            data = response.json()

            for photo in data.get("results", []):
                if photo.get("width", 0) >= min_width:
                    return {
                        "url": photo["urls"]["regular"],
                        "download_url": photo["urls"]["full"],
                        "source": "unsplash",
                        "source_url": photo["links"]["html"],
                        "photographer": photo.get("user", {}).get("name", ""),
                        "alt_text": photo.get("alt_description", query),
                        "width": photo.get("width"),
                        "height": photo.get("height"),
                    }
        except Exception as e:
            logger.debug("Unsplash search falhou: %s", e)
        return None

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
