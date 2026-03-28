import json
from typing import Any, List

from newsroom_v3.integrations.postgres_client import PostgresClient


class EpisodicMemory:
    def __init__(self, db_client: PostgresClient):
        self.db = db_client

    async def save_event(self, agent_id: str, event_type: str, content: dict[str, Any]):
        """Saves an event to the agent's episodic memory."""
        query = """
        INSERT INTO memoria_agentes (agente, tipo, conteudo, criado_em)
        VALUES (%s, 'episodica', %s, NOW())
        """
        # Add event_type to content for context
        content_with_meta = {**content, "event_type": event_type}
        await self.db.execute(query, agent_id, json.dumps(content_with_meta))

    async def recall_recent(self, agent_id: str, limit: int = 10) -> List[dict[str, Any]]:
        """Recalls the most recent events for an agent."""
        query = """
        SELECT conteudo, criado_em FROM memoria_agentes
        WHERE agente = %s AND tipo = 'episodica'
        ORDER BY criado_em DESC
        LIMIT %s
        """
        rows = await self.db.fetch(query, agent_id, limit)
        return [
            {**json.loads(row["conteudo"]), "timestamp": row["criado_em"].isoformat()}
            for row in rows
        ]
