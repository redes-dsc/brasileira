"""Conexão PostgreSQL (asyncpg) com pgvector e retry."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


async def create_pg_pool(dsn: str, min_size: int = 2, max_size: int = 10, retries: int = 5):
    """Cria pool asyncpg com retry exponencial na conexão."""
    import asyncpg

    for attempt in range(1, retries + 1):
        try:
            pool = await asyncpg.create_pool(
                dsn,
                min_size=min_size,
                max_size=max_size,
                command_timeout=30,
            )
            await ensure_pgvector(pool)
            logger.info("Pool PostgreSQL criado (min=%d, max=%d)", min_size, max_size)
            return pool
        except (OSError, asyncpg.PostgresError) as exc:
            if attempt == retries:
                raise
            wait = min(2 ** attempt, 16)
            logger.warning("PostgreSQL indisponível (tentativa %d/%d), retry em %ds: %s", attempt, retries, wait, exc)
            await asyncio.sleep(wait)


async def close_pg_pool(pool) -> None:
    """Fecha pool de conexão."""
    if pool is not None:
        await pool.close()


async def ensure_pgvector(pool) -> None:
    """Garante extensão pgvector no banco."""
    if pool is None:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    except Exception:
        logger.warning("Não foi possível criar extensão pgvector (pode já existir)")
