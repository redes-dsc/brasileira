import redis.asyncio as redis

class RedisClient:
    def __init__(self, url: str) -> None:
        self.url = url
        self._client: redis.Redis | None = None

    async def get_client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.from_url(self.url, decode_responses=True)
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def ping(self) -> bool:
        client = await self.get_client()
        return await client.ping()
