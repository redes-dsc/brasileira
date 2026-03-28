"""Entrypoint do Monitor de Concorrência V3."""

from __future__ import annotations

import asyncio
import logging
import signal
from datetime import datetime, timezone

from shared.config import load_config
from shared.kafka_client import KafkaClient
from shared.redis_client import create_redis_client
from shared.wp_client import WordPressClient

from .config import MonitorConcorrenciaConfig
from .monitor import MonitorConcorrencia

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_running = True


def _handle_signal(signum: int, _frame: object) -> None:
    """Sinaliza shutdown gracioso."""
    global _running
    logger.info("Sinal %s recebido, encerrando após ciclo atual...", signal.Signals(signum).name)
    _running = False


async def _fetch_nossos_titulos(wp: WordPressClient) -> list[str]:
    """Busca títulos recentes dos nossos artigos via WP REST API."""
    try:
        posts = await wp.get(
            "/wp-json/wp/v2/posts",
            params={"per_page": 50, "status": "publish", "orderby": "date", "order": "desc"},
        )
        if isinstance(posts, list):
            return [p["title"]["rendered"] for p in posts if "title" in p and "rendered" in p["title"]]
        return []
    except Exception:
        logger.exception("Falha ao buscar títulos do WordPress")
        return []


async def main() -> None:
    global _running

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    cfg = load_config()
    config = MonitorConcorrenciaConfig()
    cycle_seconds = config.cycle_minutes * 60

    kafka = KafkaClient(cfg.kafka_bootstrap_servers)
    await kafka.start_producer()

    redis = create_redis_client(cfg.redis_url)
    wp = WordPressClient(cfg.wp_url, cfg.wp_user, cfg.wp_auth)

    monitor = MonitorConcorrencia(kafka_client=kafka, config=config)

    logger.info("Monitor concorrência iniciado (ciclo=%dmin)", config.cycle_minutes)
    try:
        while _running:
            cycle_id = datetime.now(timezone.utc).isoformat()
            logger.info("Monitor concorrência ciclo=%s", cycle_id)
            try:
                nossos_titulos = await _fetch_nossos_titulos(wp)
                logger.info("Títulos próprios carregados: %d", len(nossos_titulos))
                published = await monitor.run_cycle(nossos_titulos)
                logger.info("Ciclo concluído: %d mensagens publicadas", published)
            except Exception:
                logger.exception("Falha no ciclo do monitor de concorrência")

            # Aguarda intervalo, mas responde rápido a shutdown
            for _ in range(cycle_seconds):
                if not _running:
                    break
                await asyncio.sleep(1)
    finally:
        logger.info("Encerrando monitor de concorrência...")
        await kafka.stop_producer()
        await wp.close()
        await redis.aclose()
        logger.info("Monitor de concorrência encerrado.")


if __name__ == "__main__":
    asyncio.run(main())
