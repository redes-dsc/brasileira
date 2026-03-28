"""Conexão Redis reutilizável com pool e autenticação."""

from __future__ import annotations

import logging
from typing import Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


def create_redis_client(
    redis_url: str,
    max_connections: int = 20,
    socket_timeout: float = 5.0,
    retry_on_timeout: bool = True,
) -> aioredis.Redis:
    """Cria cliente Redis assíncrono com pool configurável."""
    return aioredis.from_url(
        redis_url,
        decode_responses=True,
        max_connections=max_connections,
        socket_timeout=socket_timeout,
        retry_on_timeout=retry_on_timeout,
    )
