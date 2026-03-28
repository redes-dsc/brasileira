"""Entrypoint do Curador Homepage V3."""

from __future__ import annotations

import asyncio
import logging
import signal

from curador_homepage.curador import CuradorHomepageAgent
from shared.config import load_config, load_keys
from shared.db import close_pg_pool, create_pg_pool
from shared.kafka_client import KafkaClient
from shared.memory import MemoryManager
from shared.redis_client import create_redis_client
from shared.wp_client import WordPressClient
from smart_router.router import SmartLLMRouter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("curador_homepage")

CYCLE_INTERVAL_SECONDS = 900  # 15 minutos entre ciclos normais


async def _periodic(agent: CuradorHomepageAgent, shutdown: asyncio.Event) -> None:
    """Executa ciclo de curadoria a cada CYCLE_INTERVAL_SECONDS até shutdown."""
    while not shutdown.is_set():
        try:
            await agent.executar_ciclo()
        except Exception:
            logger.exception("Falha no ciclo periódico do curador")
        try:
            await asyncio.wait_for(shutdown.wait(), timeout=CYCLE_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass  # timeout expirado — hora de rodar outro ciclo


async def main() -> None:
    cfg = load_config()
    redis = create_redis_client(cfg.redis_url)
    pg_pool = await create_pg_pool(cfg.postgres_dsn, min_size=2, max_size=5)
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
    memory = MemoryManager(redis_client=redis, db_pool=pg_pool)
    agent = CuradorHomepageAgent(
        router=router, wp_client=wp, kafka_client=kafka,
        redis_client=redis, db_pool=pg_pool, memory=memory,
    )

    shutdown = asyncio.Event()

    def handle_signal(*_: object) -> None:
        logger.info("Sinal de shutdown recebido, encerrando curador_homepage...")
        shutdown.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    periodic_task = asyncio.create_task(
        _periodic(agent, shutdown), name="curador-periodic",
    )
    breaking_task = asyncio.create_task(
        agent.consumir_breaking(shutdown), name="curador-breaking",
    )
    logger.info("Curador Homepage iniciado (ciclo=%ds)", CYCLE_INTERVAL_SECONDS)

    try:
        await asyncio.gather(periodic_task, breaking_task)
    finally:
        shutdown.set()  # garantir que loops internos terminem
        periodic_task.cancel()
        breaking_task.cancel()
        await asyncio.gather(periodic_task, breaking_task, return_exceptions=True)
        await kafka.stop_producer()
        await wp.close()
        await close_pg_pool(pg_pool)
        await redis.aclose()
        logger.info("Curador Homepage encerrado.")


if __name__ == "__main__":
    asyncio.run(main())
