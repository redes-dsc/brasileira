"""Entrypoint do Editor-Chefe V3."""

from __future__ import annotations

import asyncio
import logging
import signal
from datetime import datetime, timezone

from shared.config import load_config, load_keys
from shared.db import close_pg_pool, create_pg_pool
from shared.kafka_client import KafkaClient
from shared.redis_client import create_redis_client
from shared.wp_client import WordPressClient
from smart_router.router import SmartLLMRouter

from .editor_chefe import EditorChefeObserver
from .config import EditorChefeConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    cfg = load_config()
    component_cfg = EditorChefeConfig()

    # --- Infraestrutura ---
    redis = create_redis_client(cfg.redis_url)
    pg_pool = await create_pg_pool(cfg.postgres_dsn, min_size=2, max_size=5)
    kafka = KafkaClient(cfg.kafka_bootstrap_servers)
    await kafka.start_producer()
    wp = WordPressClient(cfg.wp_url, cfg.wp_user, cfg.wp_auth)

    # --- SmartLLMRouter (para futuras análises LLM) ---
    provider_keys = {
        "openai": load_keys("OPENAI_API_KEY"),
        "anthropic": load_keys("ANTHROPIC_API_KEY"),
        "google": load_keys("GEMINI_API_KEY"),
        "xai": load_keys("XAI_API_KEY"),
        "perplexity": load_keys("PERPLEXITY_API_KEY"),
        "deepseek": load_keys("DEEPSEEK_API_KEY"),
        "alibaba": load_keys("ALIBABA_API_KEY"),
    }
    _router = SmartLLMRouter(redis_client=redis, provider_keys=provider_keys, pg_pool=pg_pool)

    # --- Observer com dados reais ---
    observer = EditorChefeObserver(
        kafka_client=kafka,
        redis_client=redis,
        wp_client=wp,
        db_pool=pg_pool,
    )

    # --- Graceful shutdown ---
    shutdown = asyncio.Event()

    def handle_signal(*_: object) -> None:
        logger.info("Sinal de shutdown recebido, finalizando...")
        shutdown.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    logger.info("Editor-Chefe iniciado (ciclo=%ds)", component_cfg.cycle_seconds)

    try:
        while not shutdown.is_set():
            cycle_id = datetime.now(timezone.utc).isoformat()
            logger.info("Editor-chefe ciclo=%s", cycle_id)
            try:
                await observer.run_cycle()
            except Exception:
                logger.exception("Falha no ciclo do editor-chefe")
            try:
                await asyncio.wait_for(shutdown.wait(), timeout=component_cfg.cycle_seconds)
            except asyncio.TimeoutError:
                pass  # timeout normal, próximo ciclo
    finally:
        logger.info("Editor-Chefe finalizando...")
        await kafka.stop_producer()
        await wp.close()
        await close_pg_pool(pg_pool)
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
