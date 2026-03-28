import json
from typing import Any, List

from newsroom_v3.integrations.postgres_client import PostgresClient


class SemanticMemory:
    def __init__(self, db_client: PostgresClient):
        self.db = db_client

    async def store(self, agent_id: str, text: str, embedding: List[float], metadata: dict[str, Any]):
        """Stores a semantic memory with vector embedding."""
        query = """
        INSERT INTO memoria_agentes (agente, tipo, conteudo, embedding, criado_em)
        VALUES (%s, 'semantica', %s, %s, NOW())
        """
        content = {"text": text, **metadata}
        await self.db.execute(query, agent_id, json.dumps(content), embedding)

    async def search(self, agent_id: str, query_embedding: List[float], limit: int = 5) -> List[dict[str, Any]]:
        """Searches for semantically similar memories using cosine similarity."""
        query = """
        SELECT conteudo, 1 - (embedding <=> %s) as similarity
        FROM memoria_agentes
        WHERE agente = %s AND tipo = 'semantica'
        ORDER BY embedding <=> %s
        LIMIT %s
        """
        rows = await self.db.fetch(query, query_embedding, agent_id, query_embedding, limit)
        return [
            {**json.loads(row["conteudo"]), "similarity": row["similarity"]}
            for row in rows
        ]
