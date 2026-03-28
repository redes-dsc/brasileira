"""Entrypoint do Revisor V3."""

from __future__ import annotations

import asyncio
import logging
import signal

from shared.config import load_config, load_keys
from shared.db import close_pg_pool, create_pg_pool
from shared.kafka_client import KafkaClient
from shared.redis_client import create_redis_client
from shared.wp_client import WordPressClient
from smart_router.router import SmartLLMRouter

from .revisor import RevisorAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("revisor")


async def main() -> None:
    cfg = load_config()
    redis = create_redis_client(cfg.redis_url)
    pg_pool = await create_pg_pool(cfg.postgres_dsn, min_size=1, max_size=5)
    kafka = KafkaClient(cfg.kafka_bootstrap_servers)
    wp = WordPressClient(cfg.wp_url, cfg.wp_user, cfg.wp_auth)

    provider_keys = {
        "openai": load_keys("OPENAI_API_KEY"),
        "anthropic": load_keys("ANTHROPIC_API_KEY"),
        "google": load_keys("GEMINI_API_KEY"),
        "deepseek": load_keys("DEEPSEEK_API_KEY"),
    }
    router = SmartLLMRouter(redis_client=redis, provider_keys=provider_keys, pg_pool=pg_pool)

    agent = RevisorAgent(wp_client=wp, router=router, redis=redis, pg_pool=pg_pool, kafka=kafka)

    shutdown = asyncio.Event()
    def handle_signal(*_):
        shutdown.set()
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    logger.info("Revisor iniciado")
    try:
        await agent.consumir()
    finally:
        await wp.close()
        await close_pg_pool(pg_pool)
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
