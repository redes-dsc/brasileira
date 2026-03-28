"""Entrypoint do Smart Router V3."""

from __future__ import annotations

import asyncio
import logging

from shared.config import load_config, load_keys
from shared.db import close_pg_pool, create_pg_pool
from shared.redis_client import create_redis_client
from smart_router.router import SmartLLMRouter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    cfg = load_config()
    redis = create_redis_client(cfg.redis_url)
    pg_pool = await create_pg_pool(cfg.postgres_dsn, min_size=1, max_size=3)
    provider_keys = {
        "openai": load_keys("OPENAI_API_KEY"),
        "anthropic": load_keys("ANTHROPIC_API_KEY"),
        "google": load_keys("GEMINI_API_KEY"),
        "xai": load_keys("XAI_API_KEY"),
        "perplexity": load_keys("PERPLEXITY_API_KEY"),
        "deepseek": load_keys("DEEPSEEK_API_KEY"),
        "alibaba": load_keys("ALIBABA_API_KEY"),
    }
    router = SmartLLMRouter(redis_client=redis, provider_keys=provider_keys, pg_pool=pg_pool)
    dashboard = await router.get_health_dashboard()
    logger.info("Smart Router pronto. providers=%d", len(dashboard.get("providers", {})))
    try:
        while True:
            await asyncio.sleep(60)
    finally:
        await close_pg_pool(pg_pool)
        await redis.close()


if __name__ == "__main__":
    asyncio.run(main())
