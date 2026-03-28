"""Entrypoint do Worker Pool V3."""

from __future__ import annotations

import asyncio
import logging

from shared.config import load_config
from shared.db import close_pg_pool, create_pg_pool
from shared.redis_client import create_redis_client
from worker_pool.collector import WorkerPool
from worker_pool.feed_scheduler import FeedScheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    cfg = load_config()
    redis = create_redis_client(cfg.redis_url)
    pg_pool = await create_pg_pool(cfg.postgres_dsn, min_size=1, max_size=5)

    worker_pool = WorkerPool(
        kafka_bootstrap=cfg.kafka_bootstrap_servers,
        num_workers=cfg.ingestion_num_workers,
        db_pool=pg_pool,
        redis_client=redis,
    )
    scheduler = FeedScheduler(
        kafka_bootstrap=cfg.kafka_bootstrap_servers,
        db_pool=pg_pool,
        health_tracker=worker_pool.health_tracker,
        cycle_interval=cfg.ingestion_cycle_interval,
    )

    await worker_pool.start()
    scheduler_task = asyncio.create_task(scheduler.run_forever(), name="feed-scheduler")
    logger.info("Worker Pool iniciado com %d workers", cfg.ingestion_num_workers)
    try:
        await scheduler_task
    finally:
        scheduler_task.cancel()
        await asyncio.gather(scheduler_task, return_exceptions=True)
        await scheduler.stop()
        await worker_pool.stop()
        await close_pg_pool(pg_pool)
        await redis.close()


if __name__ == "__main__":
    asyncio.run(main())
