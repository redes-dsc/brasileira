"""Entrypoint: consome raw-articles, classifica, produz classified-articles."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from typing import Any

from shared.config import load_config, load_keys
from shared.db import close_pg_pool, create_pg_pool
from shared.kafka_client import KafkaClient
from shared.redis_client import create_redis_client
from smart_router.router import SmartLLMRouter

from .classifier import MLClassifier
from .ner_extractor import NERExtractor
from .relevance_scorer import RelevanceScorer
from .pipeline import ClassificationPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("classificador")

BATCH_SIZE = 50
DLQ_TOPIC = "dlq-articles"


async def process_batch(
    messages: list[Any],
    pipeline: ClassificationPipeline,
    kafka: KafkaClient,
) -> int:
    """Processa batch de mensagens em paralelo."""
    tasks = []
    for msg in messages:
        tasks.append(process_single(msg.value, pipeline, kafka))
    results = await asyncio.gather(*tasks, return_exceptions=True)

    success_count = 0
    for msg, result in zip(messages, results):
        if isinstance(result, Exception):
            logger.error("Falha ao classificar artigo: %s", result, exc_info=result)
            # DLQ
            try:
                await kafka.send(DLQ_TOPIC, {
                    "original": msg.value,
                    "error": str(result),
                    "stage": "classificacao",
                })
            except Exception:
                logger.error("Falha ao enviar para DLQ", exc_info=True)
        else:
            success_count += 1
    return success_count


async def process_single(
    payload: dict[str, Any],
    pipeline: ClassificationPipeline,
    kafka: KafkaClient,
) -> None:
    """Processa um artigo individual."""
    result = await pipeline.classify(payload)
    if result:
        key = result.get("url_hash", result.get("fonte_id", "unknown"))
        await kafka.send("classified-articles", result, key=str(key))


async def main() -> None:
    cfg = load_config()
    redis = create_redis_client(cfg.redis_url)
    pg_pool = await create_pg_pool(cfg.postgres_dsn, min_size=1, max_size=5)

    kafka = KafkaClient(cfg.kafka_bootstrap_servers)
    await kafka.start_producer()

    # Router para LLM fallback
    provider_keys = {
        "openai": load_keys("OPENAI_API_KEY"),
        "google": load_keys("GEMINI_API_KEY"),
        "deepseek": load_keys("DEEPSEEK_API_KEY"),
        "alibaba": load_keys("ALIBABA_API_KEY"),
    }
    router = SmartLLMRouter(redis_client=redis, provider_keys=provider_keys, pg_pool=pg_pool)

    # Componentes
    classifier = MLClassifier()
    await classifier.initialize()
    ner = NERExtractor()
    await ner.initialize()
    scorer = RelevanceScorer()

    pipeline = ClassificationPipeline(
        classifier=classifier,
        ner_extractor=ner,
        scorer=scorer,
        router=router,
    )

    consumer = kafka.build_consumer("raw-articles", group_id="classificador-pipeline")
    await consumer.start()

    shutdown = asyncio.Event()

    def handle_signal(*_):
        shutdown.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    logger.info("Classificador iniciado, consumindo raw-articles...")
    try:
        while not shutdown.is_set():
            batch = await consumer.getmany(timeout_ms=1000, max_records=BATCH_SIZE)
            if not batch:
                continue
            messages = []
            for tp, msgs in batch.items():
                messages.extend(msgs)
            if not messages:
                continue

            count = await process_batch(messages, pipeline, kafka)
            await KafkaClient.commit_safe(consumer)
            logger.info("Batch processado: %d/%d sucesso", count, len(messages))
    finally:
        await consumer.stop()
        await kafka.stop_producer()
        await close_pg_pool(pg_pool)
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
