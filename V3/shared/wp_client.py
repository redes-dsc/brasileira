"""Cliente assíncrono para WordPress REST API."""

from __future__ import annotations

import asyncio
import base64
from typing import Any, Optional

import httpx


class WordPressClient:
    """Cliente com retry exponencial para operações no WP."""

    def __init__(self, base_url: str, user: str, app_password: str, timeout: float = 30.0):
        auth = base64.b64encode(f"{user}:{app_password}".encode("utf-8")).decode("utf-8")
        self._headers = {
            "Authorization": f"Basic {auth}",
            "User-Agent": "BrasileiraNewsBot/3.0",
        }
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        """Encerra HTTP client."""

        await self._client.aclose()

    async def request(
        self,
        method: str,
        endpoint: str,
        json: Optional[dict[str, Any]] = None,
        files: Optional[dict[str, Any]] = None,
        retries: int = 3,
    ) -> dict[str, Any]:
        """Executa request com retry para 429/5xx e erros transitórios."""

        url = f"{self._base_url}{endpoint}"
        last_error: Optional[Exception] = None
        for attempt in range(1, retries + 1):
            try:
                response = await self._client.request(
                    method=method,
                    url=url,
                    headers=self._headers,
                    json=json,
                    files=files,
                )
                if response.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError(
                        f"HTTP transitório {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                return response.json() if response.content else {}
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt == retries:
                    break
                await asyncio.sleep(min(2 ** attempt, 8))
        raise RuntimeError(f"Falha na chamada WordPress {method} {endpoint}: {last_error}")

    async def post(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        return await self.request("POST", endpoint, **kwargs)

    async def patch(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        return await self.request("PATCH", endpoint, **kwargs)

    async def get(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        return await self.request("GET", endpoint, **kwargs)
