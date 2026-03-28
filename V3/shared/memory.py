"""Memória em 3 camadas: working (Redis TTL), episódica (PostgreSQL JSONB), semântica (pgvector)."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class MemoryManager:
    """Gerencia armazenamento e recuperação de memória por agente."""

    def __init__(self, redis_client=None, db_pool=None):
        self.redis = redis_client
        self.db_pool = db_pool

    # ── Working Memory (Redis TTL) ──

    async def set_working(self, agent: str, cycle: str, payload: dict[str, Any], ttl_seconds: int = 14400) -> None:
        """Define memória de trabalho em Redis com TTL."""
        if self.redis is None:
            return
        key = f"agent:working_memory:{agent}:{cycle}"
        await self.redis.set(key, json.dumps(payload, ensure_ascii=False, default=str), ex=ttl_seconds)

    async def get_working(self, agent: str, cycle: str) -> Optional[dict[str, Any]]:
        """Lê memória de trabalho."""
        if self.redis is None:
            return None
        key = f"agent:working_memory:{agent}:{cycle}"
        raw = await self.redis.get(key)
        return json.loads(raw) if raw else None

    async def delete_working(self, agent: str, cycle: str) -> None:
        """Remove memória de trabalho de um ciclo."""
        if self.redis is None:
            return
        key = f"agent:working_memory:{agent}:{cycle}"
        await self.redis.delete(key)

    # ── Episodic Memory (PostgreSQL JSONB) ──

    async def add_episodic(self, agent: str, conteudo: dict[str, Any], relevancia_score: float = 0.5) -> None:
        """Persiste memória episódica em PostgreSQL."""
        if self.db_pool is None:
            return
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO memoria_agentes (agente, tipo, conteudo, relevancia_score)
                    VALUES ($1, 'episodica', $2::jsonb, $3)
                    """,
                    agent,
                    json.dumps(conteudo, ensure_ascii=False, default=str),
                    relevancia_score,
                )
        except Exception:
            logger.warning("Falha ao salvar memória episódica para %s", agent, exc_info=True)

    async def query_episodic(
        self,
        agent: str,
        limit: int = 20,
        min_relevancia: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Busca memórias episódicas de um agente, mais recentes primeiro."""
        if self.db_pool is None:
            return []
        try:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT conteudo, relevancia_score, criado_em
                    FROM memoria_agentes
                    WHERE agente = $1 AND tipo = 'episodica' AND relevancia_score >= $2
                    ORDER BY criado_em DESC
                    LIMIT $3
                    """,
                    agent,
                    min_relevancia,
                    limit,
                )
                return [
                    {
                        "conteudo": json.loads(row["conteudo"]) if isinstance(row["conteudo"], str) else row["conteudo"],
                        "relevancia_score": row["relevancia_score"],
                        "criado_em": row["criado_em"].isoformat() if row["criado_em"] else None,
                    }
                    for row in rows
                ]
        except Exception:
            logger.warning("Falha ao consultar memória episódica de %s", agent, exc_info=True)
            return []

    # ── Semantic Memory (pgvector cosine similarity) ──

    async def add_semantic(
        self,
        agent: str,
        conteudo: dict[str, Any],
        embedding: list[float],
        relevancia_score: float = 0.5,
    ) -> None:
        """Persiste memória semântica com embedding pgvector."""
        if self.db_pool is None:
            return
        try:
            vector_literal = "[" + ",".join(f"{v:.8f}" for v in embedding) + "]"
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO memoria_agentes (agente, tipo, conteudo, embedding, relevancia_score)
                    VALUES ($1, 'semantica', $2::jsonb, $3::vector, $4)
                    """,
                    agent,
                    json.dumps(conteudo, ensure_ascii=False, default=str),
                    vector_literal,
                    relevancia_score,
                )
        except Exception:
            logger.warning("Falha ao salvar memória semântica para %s", agent, exc_info=True)

    async def query_semantic(
        self,
        embedding: list[float],
        limit: int = 5,
        agent: Optional[str] = None,
        min_similarity: float = 0.3,
    ) -> list[dict[str, Any]]:
        """Busca memórias semânticas por similaridade de cosseno (pgvector)."""
        if self.db_pool is None:
            return []
        try:
            vector_literal = "[" + ",".join(f"{v:.8f}" for v in embedding) + "]"
            agent_filter = "AND agente = $3" if agent else ""
            params = [vector_literal, limit]
            if agent:
                params.append(agent)

            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    f"""
                    SELECT agente, conteudo, relevancia_score,
                           1 - (embedding <=> $1::vector) AS similarity,
                           criado_em
                    FROM memoria_agentes
                    WHERE tipo = 'semantica'
                      AND embedding IS NOT NULL
                      {agent_filter}
                    ORDER BY embedding <=> $1::vector
                    LIMIT $2
                    """,
                    *params,
                )
                return [
                    {
                        "agente": row["agente"],
                        "conteudo": json.loads(row["conteudo"]) if isinstance(row["conteudo"], str) else row["conteudo"],
                        "similarity": float(row["similarity"]),
                        "relevancia_score": row["relevancia_score"],
                        "criado_em": row["criado_em"].isoformat() if row["criado_em"] else None,
                    }
                    for row in rows
                    if float(row["similarity"]) >= min_similarity
                ]
        except Exception:
            logger.warning("Falha ao consultar memória semântica", exc_info=True)
            return []

    async def search_articles(
        self,
        embedding: list[float],
        limit: int = 5,
        min_similarity: float = 0.3,
    ) -> list[dict[str, Any]]:
        """Busca artigos publicados por similaridade semântica (RAG)."""
        if self.db_pool is None:
            return []
        try:
            vector_literal = "[" + ",".join(f"{v:.8f}" for v in embedding) + "]"
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT titulo, resumo, editoria, url_fonte, wp_post_id,
                           1 - (embedding <=> $1::vector) AS similarity,
                           publicado_em
                    FROM artigos
                    WHERE embedding IS NOT NULL
                    ORDER BY embedding <=> $1::vector
                    LIMIT $2
                    """,
                    vector_literal,
                    limit,
                )
                return [
                    {
                        "titulo": row["titulo"],
                        "resumo": row["resumo"],
                        "editoria": row["editoria"],
                        "url_fonte": row["url_fonte"],
                        "wp_post_id": row["wp_post_id"],
                        "similarity": float(row["similarity"]),
                        "publicado_em": row["publicado_em"].isoformat() if row["publicado_em"] else None,
                    }
                    for row in rows
                    if float(row["similarity"]) >= min_similarity
                ]
        except Exception:
            logger.warning("Falha ao buscar artigos similares", exc_info=True)
            return []

    async def cleanup_old(self, days: int = 30) -> int:
        """Remove memórias mais antigas que N dias."""
        if self.db_pool is None:
            return 0
        try:
            async with self.db_pool.acquire() as conn:
                result = await conn.execute(
                    """
                    DELETE FROM memoria_agentes
                    WHERE criado_em < NOW() - INTERVAL '1 day' * $1
                      AND (expira_em IS NULL OR expira_em < NOW())
                    """,
                    days,
                )
                count = int(result.split()[-1]) if result else 0
                if count > 0:
                    logger.info("Limpeza: removidas %d memórias com mais de %d dias", count, days)
                return count
        except Exception:
            logger.warning("Falha na limpeza de memórias antigas", exc_info=True)
            return 0
