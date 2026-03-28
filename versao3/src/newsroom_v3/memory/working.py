import json
from typing import Any, Optional

from newsroom_v3.integrations.redis_client import RedisClient


class WorkingMemory:
    def __init__(self, redis_client: RedisClient, ttl_seconds: int = 3600):
        self.redis = redis_client
        self.ttl = ttl_seconds

    async def put(self, agent_id: str, key: str, value: Any):
        """Stores a value in the agent's working memory (short-term)."""
        client = await self.redis.get_client()
        full_key = f"memory:working:{agent_id}:{key}"
        await client.set(full_key, json.dumps(value), ex=self.ttl)

    async def get(self, agent_id: str, key: str) -> Optional[Any]:
        """Retrieves a value from working memory."""
        client = await self.redis.get_client()
        full_key = f"memory:working:{agent_id}:{key}"
        data = await client.get(full_key)
        if data:
            return json.loads(data)
        return None

    async def clear(self, agent_id: str):
        """Clears all working memory for an agent."""
        client = await self.redis.get_client()
        keys = await client.keys(f"memory:working:{agent_id}:*")
        if keys:
            await client.delete(*keys)
