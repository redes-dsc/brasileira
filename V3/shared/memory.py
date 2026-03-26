"""Memória em 3 camadas: working (Redis), episódica e semântica (PostgreSQL)."""

from __future__ import annotations

import json
from typing import Any, Optional


class MemoryManager:
    """Gerencia armazenamento e recuperação de memória por agente."""

    def __init__(self, redis_client=None, db_pool=None):
        self.redis = redis_client
        self.db_pool = db_pool

    async def set_working(self, agent: str, cycle: str, payload: dict[str, Any], ttl_seconds: int = 14400) -> None:
        """Define memória de trabalho em Redis."""

        if self.redis is None:
            raise RuntimeError("Redis indisponível para memória de trabalho")
        key = f"agent:working_memory:{agent}:{cycle}"
        await self.redis.set(key, json.dumps(payload, ensure_ascii=False), ex=ttl_seconds)

    async def get_working(self, agent: str, cycle: str) -> Optional[dict[str, Any]]:
        """Lê memória de trabalho."""

        if self.redis is None:
            return None
        key = f"agent:working_memory:{agent}:{cycle}"
        raw = await self.redis.get(key)
        return json.loads(raw) if raw else None

    async def add_episodic(self, agent: str, conteudo: dict[str, Any], relevancia_score: float = 0.5) -> None:
        """Persiste memória episódica em PostgreSQL."""

        if self.db_pool is None:
            raise RuntimeError("PostgreSQL indisponível para memória episódica")
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO memoria_agentes (agente, tipo, conteudo, relevancia_score)
                VALUES ($1, 'episodica', $2::jsonb, $3)
                """,
                agent,
                json.dumps(conteudo, ensure_ascii=False),
                relevancia_score,
            )

    async def add_semantic(
        self,
        agent: str,
        conteudo: dict[str, Any],
        embedding: list[float],
        relevancia_score: float = 0.5,
    ) -> None:
        """Persiste memória semântica em PostgreSQL com pgvector."""

        if self.db_pool is None:
            raise RuntimeError("PostgreSQL indisponível para memória semântica")
        vector_literal = "[" + ",".join(f"{value:.10f}" for value in embedding) + "]"
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO memoria_agentes (agente, tipo, conteudo, embedding, relevancia_score)
                VALUES ($1, 'semantica', $2::jsonb, $3::vector, $4)
                """,
                agent,
                json.dumps(conteudo, ensure_ascii=False),
                vector_literal,
                relevancia_score,
            )
