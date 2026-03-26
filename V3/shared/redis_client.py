"""Conexão Redis reutilizável."""

from __future__ import annotations


def create_redis_client(redis_url: str):
    """Cria cliente Redis assíncrono."""

    import redis.asyncio as redis

    return redis.from_url(redis_url, decode_responses=True)
