"""Entrypoint do Pauteiro V3."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import signal
from datetime import datetime, timezone
from html import unescape
from typing import Any

from shared.config import load_config, load_keys
from shared.db import close_pg_pool, create_pg_pool
from shared.kafka_client import KafkaClient
from shared.memory import MemoryManager
from shared.redis_client import create_redis_client
from shared.wp_client import WordPressClient

from smart_router.router import SmartLLMRouter

from .config import PauteiroConfig
from .pauteiro import PauteiroAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flag para shutdown gracioso
_shutdown = asyncio.Event()


def _request_shutdown() -> None:
    """Handler de sinal para shutdown gracioso."""
    logger.info("Sinal de shutdown recebido, encerrando...")
    _shutdown.set()


def _strip_html(text: str) -> str:
    """Remove tags HTML e decode entities de excerpts WordPress."""
    clean = re.sub(r"<[^>]+>", "", text)
    return unescape(clean).strip()


def _build_provider_keys() -> dict[str, list[str]]:
    """Carrega chaves de API de todos os providers LLM via env."""
    mapping = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "google": "GOOGLE_API_KEY",
        "xai": "XAI_API_KEY",
        "perplexity": "PERPLEXITY_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "alibaba": "ALIBABA_API_KEY",
    }
    keys: dict[str, list[str]] = {}
    for provider, env_prefix in mapping.items():
        provider_keys = load_keys(env_prefix)
        if provider_keys:
            keys[provider] = provider_keys
    return keys


async def _collect_wp_signals(wp: WordPressClient) -> list[dict[str, Any]]:
    """Coleta posts recentes do WordPress como sinais editoriais."""
    signals: list[dict[str, Any]] = []
    try:
        posts = await wp.get(
            "/wp-json/wp/v2/posts",
            params={"per_page": 50, "orderby": "date", "order": "desc"},
        )
        if not isinstance(posts, list):
            return signals
        for post in posts:
            titulo = _strip_html(post.get("title", {}).get("rendered", ""))
            resumo = _strip_html(post.get("excerpt", {}).get("rendered", ""))
            link = post.get("link", "")
            # Extrair editoria das categorias (primeiro ID como fallback)
            categories = post.get("categories", [])
            editoria = f"cat_{categories[0]}" if categories else "ultimas_noticias"
            if not titulo:
                continue
            signals.append({
                "titulo": titulo,
                "resumo": resumo,
                "editoria": editoria,
                "fonte": "wordpress_recentes",
                "score": 0.5,
                "url": link,
            })
        logger.info("Coletados %d sinais do WordPress", len(signals))
    except Exception:
        logger.exception("Falha ao coletar sinais do WordPress")
    return signals


async def _collect_redis_signals(redis_client) -> list[dict[str, Any]]:
    """Coleta dados de gaps/trending do monitor_concorrencia via Redis."""
    signals: list[dict[str, Any]] = []
    try:
        # Buscar chaves de gaps do monitor de concorrência
        gap_keys: list[str] = []
        async for key in redis_client.scan_iter(match="monitor:gaps:*", count=100):
            gap_keys.append(key)
        conc_keys: list[str] = []
        async for key in redis_client.scan_iter(match="concorrencia:results:*", count=100):
            conc_keys.append(key)

        for key in gap_keys:
            raw = await redis_client.get(key)
            if not raw:
                continue
            try:
                data = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(data, dict):
                    signals.append({
                        "titulo": data.get("titulo", data.get("topic", str(key))),
                        "resumo": data.get("resumo", data.get("description", "")),
                        "editoria": data.get("editoria", "ultimas_noticias"),
                        "fonte": "monitor_gaps",
                        "score": float(data.get("score", data.get("urgency", 0.7))),
                        "url": data.get("url", ""),
                    })
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            signals.append({
                                "titulo": item.get("titulo", item.get("topic", "")),
                                "resumo": item.get("resumo", item.get("description", "")),
                                "editoria": item.get("editoria", "ultimas_noticias"),
                                "fonte": "monitor_gaps",
                                "score": float(item.get("score", item.get("urgency", 0.7))),
                                "url": item.get("url", ""),
                            })
            except (json.JSONDecodeError, ValueError):
                logger.debug("Falha ao decodificar gap key %s", key)

        for key in conc_keys:
            raw = await redis_client.get(key)
            if not raw:
                continue
            try:
                data = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(data, dict):
                    signals.append({
                        "titulo": data.get("titulo", data.get("topic", str(key))),
                        "resumo": data.get("resumo", data.get("description", "")),
                        "editoria": data.get("editoria", "ultimas_noticias"),
                        "fonte": "concorrencia_trending",
                        "score": float(data.get("score", data.get("urgency", 0.6))),
                        "url": data.get("url", ""),
                    })
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            signals.append({
                                "titulo": item.get("titulo", item.get("topic", "")),
                                "resumo": item.get("resumo", item.get("description", "")),
                                "editoria": item.get("editoria", "ultimas_noticias"),
                                "fonte": "concorrencia_trending",
                                "score": float(item.get("score", item.get("urgency", 0.6))),
                                "url": item.get("url", ""),
                            })
            except (json.JSONDecodeError, ValueError):
                logger.debug("Falha ao decodificar concorrencia key %s", key)

        if signals:
            logger.info("Coletados %d sinais do Redis (gaps + concorrência)", len(signals))
    except Exception:
        logger.exception("Falha ao coletar sinais do Redis")
    return signals


async def _collect_kafka_signals(kafka: KafkaClient) -> list[dict[str, Any]]:
    """Opcionalmente consome sinais do tópico Kafka de sinais."""
    signals: list[dict[str, Any]] = []
    consumer = None
    try:
        consumer = kafka.build_consumer(
            topic="pautas-sinais",
            group_id="pauteiro-signals",
            auto_offset_reset="latest",
            enable_auto_commit=False,
        )
        await consumer.start()
        # Poll com timeout curto para não bloquear o ciclo
        batch = await consumer.getmany(timeout_ms=3000, max_records=50)
        for tp, messages in batch.items():
            for msg in messages:
                if isinstance(msg.value, dict):
                    signals.append({
                        "titulo": msg.value.get("titulo", ""),
                        "resumo": msg.value.get("resumo", ""),
                        "editoria": msg.value.get("editoria", "ultimas_noticias"),
                        "fonte": msg.value.get("fonte", "kafka_sinais"),
                        "score": float(msg.value.get("score", 0.5)),
                        "url": msg.value.get("url", ""),
                    })
        if batch:
            await KafkaClient.commit_safe(consumer)
        if signals:
            logger.info("Coletados %d sinais do Kafka", len(signals))
    except Exception:
        logger.debug("Tópico pautas-sinais não disponível ou erro ao consumir", exc_info=True)
    finally:
        if consumer is not None:
            try:
                await consumer.stop()
            except Exception:
                pass
    return signals


async def main() -> None:
    """Loop principal do Pauteiro com coleta de sinais reais."""
    cfg = load_config()
    component_cfg = PauteiroConfig()

    # ── Infraestrutura ──
    redis_client = create_redis_client(cfg.redis_url)
    pg_pool = await create_pg_pool(cfg.postgres_dsn)
    wp = WordPressClient(cfg.wp_url, cfg.wp_user, cfg.wp_auth)
    kafka = KafkaClient(cfg.kafka_bootstrap_servers)
    await kafka.start_producer()

    # SmartLLMRouter com chaves de provedores
    provider_keys = _build_provider_keys()
    router = SmartLLMRouter(
        redis_client=redis_client,
        provider_keys=provider_keys,
        pg_pool=pg_pool,
    )

    # Memória em 3 camadas
    memory = MemoryManager(redis_client=redis_client, db_pool=pg_pool)

    # Agente principal
    agent = PauteiroAgent(
        kafka_client=kafka,
        router=router,
        memory=memory,
        config=component_cfg,
    )

    # Signal handlers para shutdown gracioso
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _request_shutdown)

    logger.info(
        "Pauteiro iniciado (ciclo=%ds, max_sinais=%d)",
        component_cfg.cycle_interval_seconds,
        component_cfg.max_signals_per_cycle,
    )

    try:
        while not _shutdown.is_set():
            cycle_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            logger.info("Pauteiro ciclo=%s — coletando sinais...", cycle_id)
            try:
                # Coletar sinais de múltiplas fontes em paralelo
                wp_result, redis_result, kafka_result = await asyncio.gather(
                    _collect_wp_signals(wp),
                    _collect_redis_signals(redis_client),
                    _collect_kafka_signals(kafka),
                    return_exceptions=True,
                )

                # Tratar exceções que vazaram do gather
                all_signals: list[dict[str, Any]] = []
                for source_name, result in [
                    ("wordpress", wp_result),
                    ("redis", redis_result),
                    ("kafka", kafka_result),
                ]:
                    if isinstance(result, Exception):
                        logger.error("Falha na coleta %s: %s", source_name, result)
                    elif isinstance(result, list):
                        all_signals.extend(result)

                logger.info(
                    "Ciclo %s: %d sinais coletados (wp=%s redis=%s kafka=%s)",
                    cycle_id,
                    len(all_signals),
                    len(wp_result) if isinstance(wp_result, list) else "erro",
                    len(redis_result) if isinstance(redis_result, list) else "erro",
                    len(kafka_result) if isinstance(kafka_result, list) else "erro",
                )

                pautas = await agent.run_cycle(all_signals, cycle_id)
                logger.info("Ciclo %s: %d pautas geradas", cycle_id, len(pautas))
            except Exception:
                logger.exception("Falha no ciclo do pauteiro %s", cycle_id)

            # Aguarda intervalo ou shutdown (o que vier primeiro)
            try:
                await asyncio.wait_for(
                    _shutdown.wait(),
                    timeout=component_cfg.cycle_interval_seconds,
                )
            except asyncio.TimeoutError:
                pass  # Timeout normal, próximo ciclo
    finally:
        logger.info("Encerrando Pauteiro — cleanup de recursos...")
        await kafka.stop_producer()
        await wp.close()
        await close_pg_pool(pg_pool)
        try:
            await redis_client.aclose()
        except Exception:
            logger.debug("Erro ao fechar Redis", exc_info=True)
        logger.info("Pauteiro encerrado.")


if __name__ == "__main__":
    asyncio.run(main())
