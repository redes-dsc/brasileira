"""Tier 3: Geração de imagem por IA (gpt-image-1 ou DALL-E)."""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class Tier3Generator:
    """Gera imagens via API de IA generativa."""

    def __init__(self):
        self.openai_key = os.getenv("OPENAI_API_KEY", "")
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    async def generate(self, prompt: str, editoria: str = "") -> dict[str, Any]:
        """Gera imagem via OpenAI Images API."""
        if not self.openai_key:
            return {"success": False, "reason": "OPENAI_API_KEY não configurada", "tier": 3}

        try:
            client = await self._get_client()
            response = await client.post(
                "https://api.openai.com/v1/images/generations",
                headers={"Authorization": f"Bearer {self.openai_key}"},
                json={
                    "model": "gpt-image-1",
                    "prompt": f"Foto jornalística editorial, estilo fotojornalismo profissional: {prompt}",
                    "n": 1,
                    "size": "1024x1024",
                    "quality": "high",
                },
            )
            response.raise_for_status()
            data = response.json()
            images = data.get("data", [])
            if images:
                url = images[0].get("url", "")
                if url:
                    return {
                        "success": True,
                        "url": url,
                        "source": "gpt-image-1",
                        "ai_generated": True,
                        "ai_label": "Imagem gerada por inteligência artificial",
                        "tier": 3,
                    }
        except Exception:
            logger.warning("Geração de imagem falhou", exc_info=True)

        return {"success": False, "reason": "geração de imagem falhou", "tier": 3}

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
