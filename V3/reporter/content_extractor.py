"""Extração de conteúdo com fallback para resumo."""

from __future__ import annotations

import asyncio

import httpx
from bs4 import BeautifulSoup


async def extrair_conteudo_fonte(url: str, resumo_original: str, timeout: float = 12.0) -> dict[str, str]:
    """Extrai conteúdo textual da URL; se falhar, usa resumo."""

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        text = " ".join(part.strip() for part in soup.stripped_strings)
        text = text[:12000]
        if not text:
            raise ValueError("Conteúdo vazio após parsing")
        return {"conteudo": text, "extracao_metodo": "http_html"}
    except Exception:
        return {"conteudo": resumo_original or "", "extracao_metodo": "fallback_resumo"}
