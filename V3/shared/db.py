"""Conexão PostgreSQL (asyncpg) compartilhada."""

from __future__ import annotations

from typing import Optional


async def create_pg_pool(dsn: str, min_size: int = 2, max_size: int = 10):
    """Cria pool asyncpg com parâmetros padrão do projeto."""

    import asyncpg

    return await asyncpg.create_pool(dsn, min_size=min_size, max_size=max_size)


async def close_pg_pool(pool) -> None:
    """Fecha pool de conexão."""

    if pool is not None:
        await pool.close()


async def ensure_pgvector(pool) -> None:
    """Garante extensão pgvector no banco."""

    if pool is None:
        return
    async with pool.acquire() as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
