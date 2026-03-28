"""Entrypoint do Monitor de Sistema V3."""

from __future__ import annotations

import asyncio
import logging
import signal
from datetime import datetime, timedelta, timezone

from shared.config import load_config
from shared.db import create_pg_pool, close_pg_pool
from shared.redis_client import create_redis_client
from shared.wp_client import WordPressClient

from .monitor_sistema import MonitorSistema

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_running = True
_CYCLE_SECONDS = 60


def _handle_signal(signum: int, _frame: object) -> None:
    """Sinaliza shutdown gracioso."""
    global _running
    logger.info("Sinal %s recebido, encerrando após ciclo atual...", signal.Signals(signum).name)
    _running = False


async def _fetch_artigos_ultima_hora(wp: WordPressClient) -> int:
    """Consulta WP REST API para contar artigos publicados na última hora."""
    try:
        one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        posts = await wp.get(
            "/wp-json/wp/v2/posts",
            params={"after": one_hour_ago, "status": "publish", "per_page": 100},
        )
        if isinstance(posts, list):
            return len(posts)
        return 0
    except Exception:
        logger.exception("Falha ao buscar artigos recentes do WordPress")
        return 0


async def _fetch_fontes(pg_pool) -> list[dict]:
    """Consulta tabela fontes no PostgreSQL para fontes ativas."""
    try:
        async with pg_pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM fontes WHERE ativa = true")
            return [dict(row) for row in rows]
    except Exception:
        logger.exception("Falha ao buscar fontes do PostgreSQL")
        return []


async def main() -> None:
    global _running

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    cfg = load_config()

    redis = create_redis_client(cfg.redis_url)
    pg_pool = await create_pg_pool(cfg.postgres_dsn)
    wp = WordPressClient(cfg.wp_url, cfg.wp_user, cfg.wp_auth)

    monitor = MonitorSistema(redis_client=redis)

    logger.info("Monitor sistema iniciado (ciclo=%ds)", _CYCLE_SECONDS)
    try:
        while _running:
            cycle_id = datetime.now(timezone.utc).isoformat()
            logger.info("Monitor-sistema ciclo=%s", cycle_id)
            try:
                artigos_ultima_hora = await _fetch_artigos_ultima_hora(wp)
                fontes = await _fetch_fontes(pg_pool)
                logger.info("Dados coletados: artigos_1h=%d fontes_ativas=%d", artigos_ultima_hora, len(fontes))

                await monitor.run_cycle(
                    published_events=artigos_ultima_hora,
                    fontes=fontes,
                    custo_hora=0.0,
                )
            except Exception:
                logger.exception("Falha no ciclo do monitor-sistema")

            # Aguarda intervalo, mas responde rápido a shutdown
            for _ in range(_CYCLE_SECONDS):
                if not _running:
                    break
                await asyncio.sleep(1)
    finally:
        logger.info("Encerrando monitor de sistema...")
        await wp.close()
        await close_pg_pool(pg_pool)
        await redis.aclose()
        logger.info("Monitor de sistema encerrado.")


if __name__ == "__main__":
    asyncio.run(main())
