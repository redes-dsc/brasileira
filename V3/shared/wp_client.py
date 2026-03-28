"""Cliente assíncrono para WordPress REST API."""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any, Optional, Union

import httpx

logger = logging.getLogger(__name__)


class WordPressClient:
    """Cliente com retry exponencial para operações no WP."""

    def __init__(self, base_url: str, user: str, app_password: str, timeout: float = 30.0):
        auth = base64.b64encode(f"{user}:{app_password}".encode("utf-8")).decode("utf-8")
        self._headers = {
            "Authorization": f"Basic {auth}",
            "User-Agent": "BrasileiraNewsBot/3.0",
        }
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout, http2=True)

    async def close(self) -> None:
        """Encerra HTTP client."""
        await self._client.aclose()

    async def request(
        self,
        method: str,
        endpoint: str,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
        files: Optional[Any] = None,
        retries: int = 3,
    ) -> Union[dict[str, Any], list[Any]]:
        """Executa request com retry para 429/5xx e erros transitórios."""
        url = f"{self._base_url}{endpoint}"
        last_error: Optional[Exception] = None
        for attempt in range(1, retries + 1):
            try:
                kwargs: dict[str, Any] = {
                    "method": method,
                    "url": url,
                    "headers": self._headers,
                }
                if json is not None:
                    kwargs["json"] = json
                if params is not None:
                    kwargs["params"] = params
                if files is not None:
                    kwargs["files"] = files

                response = await self._client.request(**kwargs)
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
                wait = min(2 ** attempt, 16)
                logger.warning("WP %s %s tentativa %d/%d falhou: %s (retry em %ds)", method, endpoint, attempt, retries, exc, wait)
                await asyncio.sleep(wait)
        raise RuntimeError(f"Falha na chamada WordPress {method} {endpoint}: {last_error}")

    async def post(self, endpoint: str, **kwargs: Any) -> Union[dict[str, Any], list[Any]]:
        return await self.request("POST", endpoint, **kwargs)

    async def patch(self, endpoint: str, **kwargs: Any) -> Union[dict[str, Any], list[Any]]:
        return await self.request("PATCH", endpoint, **kwargs)

    async def get(self, endpoint: str, **kwargs: Any) -> Union[dict[str, Any], list[Any]]:
        return await self.request("GET", endpoint, **kwargs)

    async def delete(self, endpoint: str, **kwargs: Any) -> Union[dict[str, Any], list[Any]]:
        return await self.request("DELETE", endpoint, **kwargs)

    async def upload_media(self, file_data: bytes, filename: str, mime_type: str = "image/jpeg") -> dict[str, Any]:
        """Upload de mídia para WordPress."""
        headers = {**self._headers, "Content-Disposition": f'attachment; filename="{filename}"', "Content-Type": mime_type}
        response = await self._client.post(
            f"{self._base_url}/wp-json/wp/v2/media",
            headers=headers,
            content=file_data,
        )
        response.raise_for_status()
        return response.json()
