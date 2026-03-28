"""Entrypoint: consome article-published, processa imagens via 4 tiers."""

from __future__ import annotations

import asyncio
import logging
import signal
from datetime import datetime, timezone
from typing import Any

from shared.config import load_config, load_keys
from shared.kafka_client import KafkaClient
from shared.redis_client import create_redis_client
from shared.wp_client import WordPressClient
from smart_router.router import SmartLLMRouter

from .fotografo import FotografoAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("fotografo")


async def main() -> None:
    cfg = load_config()
    redis = create_redis_client(cfg.redis_url)

    kafka = KafkaClient(cfg.kafka_bootstrap_servers)
    await kafka.start_producer()

    wp = WordPressClient(cfg.wp_url, cfg.wp_user, cfg.wp_auth)

    provider_keys = {
        "openai": load_keys("OPENAI_API_KEY"),
        "anthropic": load_keys("ANTHROPIC_API_KEY"),
        "google": load_keys("GEMINI_API_KEY"),
    }
    router = SmartLLMRouter(redis_client=redis, provider_keys=provider_keys)

    agent = FotografoAgent(router=router)
    consumer = kafka.build_consumer("article-published", group_id="fotografo-pipeline")
    await consumer.start()

    shutdown = asyncio.Event()
    def handle_signal(*_):
        shutdown.set()
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    logger.info("Fotógrafo iniciado, consumindo article-published...")
    try:
        while not shutdown.is_set():
            batch = await consumer.getmany(timeout_ms=1000, max_records=5)
            if not batch:
                continue
            for tp, messages in batch.items():
                for msg in messages:
                    await process_event(msg.value, agent, wp, kafka)
            await KafkaClient.commit_safe(consumer)
    finally:
        await consumer.stop()
        await kafka.stop_producer()
        await agent.close()
        await wp.close()
        await redis.aclose()


async def process_event(event: dict[str, Any], agent: FotografoAgent, wp: WordPressClient, kafka: KafkaClient):
    """Processa um evento article-published."""
    wp_post_id = event.get("wp_post_id")
    try:
        result = await agent.processar(event)
        image_url = result.get("image_url", "")

        if image_url and wp_post_id:
            # Upload ou attach imagem ao post
            await attach_image_to_post(wp, wp_post_id, result)
            logger.info("Imagem attached: wp_post_id=%s tier=%s source=%s", wp_post_id, result.get("tier"), result.get("source"))
    except Exception:
        logger.error("Falha ao processar imagem para wp_post_id=%s", wp_post_id, exc_info=True)


async def attach_image_to_post(wp: WordPressClient, wp_post_id: int, image_result: dict[str, Any]):
    """Faz upload da imagem e seta como featured_media no post."""
    import httpx
    image_url = image_result["image_url"]

    # Se é URL relativa (placeholder), só associar
    if image_url.startswith("/"):
        logger.info("Placeholder local para wp_post_id=%d", wp_post_id)
        return

    try:
        # Download da imagem
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(image_url)
            resp.raise_for_status()
            image_data = resp.content

        # Determinar extensão
        content_type = resp.headers.get("content-type", "image/jpeg")
        ext = "jpg"
        if "png" in content_type:
            ext = "png"
        elif "webp" in content_type:
            ext = "webp"

        filename = f"featured-{wp_post_id}.{ext}"

        # Upload para WordPress
        media = await wp.upload_media(image_data, filename, content_type)
        media_id = media.get("id")

        if media_id:
            # Set featured_media
            alt_text = image_result.get("alt", "")
            if image_result.get("ai_generated"):
                alt_text = image_result.get("ai_label", "Imagem gerada por IA")

            await wp.patch(f"/wp-json/wp/v2/posts/{wp_post_id}", json={"featured_media": media_id})
            if alt_text:
                await wp.post(f"/wp-json/wp/v2/media/{media_id}", json={"alt_text": alt_text})
    except Exception:
        logger.error("Falha ao fazer upload/attach imagem para wp_post_id=%d", wp_post_id, exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
