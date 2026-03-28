"""Entrypoint: consome classified-articles + pautas, produz article-published."""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Any

from shared.config import load_config, load_keys
from shared.db import close_pg_pool, create_pg_pool
from shared.kafka_client import KafkaClient
from shared.memory import MemoryManager
from shared.redis_client import create_redis_client
from shared.wp_client import WordPressClient
from smart_router.router import SmartLLMRouter

from .reporter import ReporterAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("reporter")

TOPICS = ["classified-articles", "pautas-especiais", "pautas-gap"]
DLQ_TOPIC = "dlq-articles"


async def consume_topic(
    topic: str,
    kafka: KafkaClient,
    agent: ReporterAgent,
    shutdown: asyncio.Event,
):
    """Consumer loop para um tópico específico."""
    consumer = kafka.build_consumer(topic, group_id=f"reporter-{topic}")
    await consumer.start()
    logger.info("Reporter consumer iniciado: %s", topic)
    try:
        while not shutdown.is_set():
            batch = await consumer.getmany(timeout_ms=1000, max_records=10)
            if not batch:
                continue
            for tp, messages in batch.items():
                for msg in messages:
                    await process_message(msg.value, kafka, agent, topic)
            await KafkaClient.commit_safe(consumer)
    finally:
        await consumer.stop()


async def process_message(payload: dict[str, Any], kafka: KafkaClient, agent: ReporterAgent, source_topic: str):
    """Processa uma mensagem individual com error handling."""
    try:
        result = await agent.processar(payload)
        if result and result.get("wp_post_id"):
            await kafka.send(
                "article-published",
                result,
                key=str(result["wp_post_id"]),
            )
            logger.info("Artigo publicado: wp_post_id=%d fonte=%s", result["wp_post_id"], source_topic)
    except Exception:
        logger.error("Falha ao processar artigo de %s: %s", source_topic, payload.get("titulo", "?")[:60], exc_info=True)
        try:
            await kafka.send(DLQ_TOPIC, {
                "original": payload,
                "error": "reporter_processing_failed",
                "source_topic": source_topic,
            })
        except Exception:
            logger.error("Falha ao enviar para DLQ", exc_info=True)


async def main() -> None:
    cfg = load_config()
    redis = create_redis_client(cfg.redis_url)
    pg_pool = await create_pg_pool(cfg.postgres_dsn, min_size=2, max_size=10)

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

    agent = ReporterAgent(router=router, wp_client=wp, memory=memory, pg_pool=pg_pool)

    shutdown = asyncio.Event()

    def handle_signal(*_):
        shutdown.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    # Consumir 3 tópicos em paralelo
    tasks = [
        asyncio.create_task(consume_topic(topic, kafka, agent, shutdown))
        for topic in TOPICS
    ]
    logger.info("Reporter iniciado, consumindo: %s", TOPICS)

    try:
        await asyncio.gather(*tasks)
    finally:
        await kafka.stop_producer()
        await wp.close()
        await close_pg_pool(pg_pool)
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
