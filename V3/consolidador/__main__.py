"""Entrypoint do Consolidador V3."""

from __future__ import annotations

import asyncio
import logging
import signal

from consolidador.consolidador import ConsolidadorAgent
from shared.config import load_config, load_keys
from shared.db import close_pg_pool, create_pg_pool
from shared.kafka_client import KafkaClient
from shared.redis_client import create_redis_client
from shared.wp_client import WordPressClient
from smart_router.router import SmartLLMRouter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("consolidador")


async def main() -> None:
    cfg = load_config()
    redis = create_redis_client(cfg.redis_url)
    pg_pool = await create_pg_pool(cfg.postgres_dsn, min_size=1, max_size=3)

    kafka = KafkaClient(cfg.kafka_bootstrap_servers)
    await kafka.start_producer()

    wp = WordPressClient(cfg.wp_url, cfg.wp_user, cfg.wp_auth)
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
    agent = ConsolidadorAgent(router=router, wp_client=wp, kafka_client=kafka, redis_client=redis, db_pool=pg_pool)

    shutdown = asyncio.Event()

    def handle_signal(*_):
        logger.info("Sinal de shutdown recebido, encerrando consolidador...")
        shutdown.set()
        agent.stop()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    logger.info("Consolidador iniciado, consumindo tópico consolidacao...")
    try:
        await agent.consumir()
    finally:
        await kafka.stop_producer()
        await wp.close()
        await close_pg_pool(pg_pool)
        await redis.aclose()
        logger.info("Consolidador encerrado.")


if __name__ == "__main__":
    asyncio.run(main())
