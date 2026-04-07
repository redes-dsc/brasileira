"""Curador V4 — Orquestrador principal do editor-chefe algorítmico.

Executa ciclos periódicos de curadoria da homepage:
  1. Scan de posts recentes
  2. Scoring objetivo + editorial (LLM PREMIUM)
  3. Detecção de macrotemas
  4. Composição do layout
  5. Cálculo de diff
  6. Aplicação no WordPress
  7. Logging no Supabase
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from typing import Any

import httpx

# Garantir que imports V3 funcionem a partir do diretório raiz do servidor
sys.path.insert(0, "/home/bitnami")

import redis.asyncio as aioredis

from curador_v4.applicator import apply_layout, manage_macrotemas
from curador_v4.compositor import compose_layout
from curador_v4.config import CuradorConfig, load_config
from curador_v4.differ import calculate_diff
from curador_v4.logger import log_cycle
from curador_v4.macrotema_detector import detect_macrotemas
from curador_v4.presets import BST, get_current_preset
from curador_v4.scanner import scan_recent_posts
from curador_v4.scorer import score_posts

# Importar cliente WP da V3
try:
    from V3.shared.wp_client import WordPressClient
except ImportError:
    # Fallback: reimplementação mínima se V3 não estiver disponível
    WordPressClient = None  # type: ignore[assignment,misc]

logger = logging.getLogger("curador_v4")

# Configuração do lock distribuído
LOCK_KEY = "curador_v4:lock"
LOCK_TTL = 120  # segundos


async def _acquire_lock(redis_client: aioredis.Redis) -> bool:
    """Adquire lock distribuído via Redis SET NX EX."""
    return await redis_client.set(LOCK_KEY, "1", nx=True, ex=LOCK_TTL)


async def _release_lock(redis_client: aioredis.Redis) -> None:
    """Libera lock distribuído."""
    await redis_client.delete(LOCK_KEY)


def _create_wp_client(config: CuradorConfig) -> Any:
    """Cria instância do WordPressClient (V3 ou fallback)."""

    if WordPressClient is not None:
        return WordPressClient(config.wp_base_url, config.wp_user, config.wp_app_password)

    # Fallback mínimo se V3 não disponível
    from V3.shared.wp_client import WordPressClient as WPC
    return WPC(config.wp_base_url, config.wp_user, config.wp_app_password)


async def run_cycle(
    config: CuradorConfig,
    wp_client: Any,
    redis_client: aioredis.Redis,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Executa um ciclo completo de curadoria da homepage."""

    start = time.monotonic()
    preset = get_current_preset()
    logger.info(
        "Ciclo iniciado — preset: %s (%d-%d blocos)",
        preset.name, preset.min_blocks, preset.max_blocks,
    )

    # 1. Scan de posts recentes
    try:
        posts = await scan_recent_posts(wp_client, hours_back=config.scan_hours_back)
    except Exception as exc:
        logger.error("Falha no scan de posts: %s", exc)
        posts = []

    logger.info("Scan: %d posts coletados", len(posts))

    if not posts:
        logger.warning("Nenhum post encontrado — ciclo abortado")
        return _cycle_result(config, preset, start, posts=[], dry_run=dry_run, success=False)

    # 2. Scoring
    try:
        scored = await score_posts(config, posts)
    except Exception as exc:
        logger.error("Falha no scoring: %s", exc)
        scored = posts  # Continuar sem scores editoriais

    logger.info("Score: %d posts pontuados", len(scored))

    # 3. Detecção de macrotemas
    try:
        macrotemas = detect_macrotemas(
            scored,
            min_posts=config.macrotema_min_posts,
            min_categories=config.macrotema_min_categories,
        )
    except Exception as exc:
        logger.error("Falha na detecção de macrotemas: %s", exc)
        macrotemas = []

    logger.info("Macrotemas: %d detectados", len(macrotemas))

    # 4. Obter layout atual
    current: dict[str, Any] | None = None
    try:
        current = await wp_client.get(f"/wp-json/brasileira/v1/layout/{config.homepage_page_id}")
        if not isinstance(current, dict):
            current = None
    except Exception:
        logger.debug("Layout atual não encontrado — será criado do zero")

    # 5. Composição do layout
    try:
        proposed = await compose_layout(config, scored, macrotemas, preset, current)
    except Exception as exc:
        logger.error("Falha na composição: %s", exc)
        return _cycle_result(config, preset, start, posts=scored, dry_run=dry_run, success=False)

    logger.info("Composição: %d blocos propostos", len(proposed.get("blocks", [])))

    # 6. Diff
    diff = calculate_diff(current, proposed)
    logger.info(
        "Diff: método=%s, mudanças=%s",
        diff["method"], diff.get("changes", {}),
    )

    # 7. Aplicar
    success = True
    if dry_run:
        logger.info(
            "DRY-RUN — layout proposto:\n%s",
            json.dumps(proposed, indent=2, ensure_ascii=False)[:3000],
        )
    else:
        changes = diff.get("changes", {})
        has_changes = (
            changes.get("added", 0) > 0
            or changes.get("removed", 0) > 0
            or changes.get("updated", 0) > 0
            or diff["method"] == "PUT"
        )

        if has_changes:
            try:
                success = await apply_layout(wp_client, config, config.homepage_page_id, diff)
            except Exception as exc:
                logger.error("Falha ao aplicar layout: %s", exc)
                success = False

            # Gerenciar macrotemas
            try:
                current_mt = [
                    b["config"] for b in (current or {}).get("blocks", [])
                    if b.get("type") == "macrotema" and "config" in b
                ]
                await manage_macrotemas(wp_client, config, current_mt, macrotemas)
            except Exception as exc:
                logger.warning("Falha ao gerenciar macrotemas: %s", exc)
        else:
            logger.info("Sem mudanças — layout mantido")

    duration = time.monotonic() - start

    # 8. Logging no Supabase
    cycle_data = {
        "cycle_id": proposed.get("cycle_id"),
        "timestamp": datetime.now(BST).isoformat(),
        "preset": preset.name,
        "posts_scanned": len(posts),
        "posts_scored": len(scored),
        "macrotemas_detected": len(macrotemas),
        "blocks_total": len(proposed.get("blocks", [])),
        "method": diff["method"],
        "changes": diff.get("changes", {}),
        "duration_seconds": round(duration, 2),
        "success": success,
        "dry_run": dry_run,
    }

    if not dry_run:
        try:
            await log_cycle(config, cycle_data)
        except Exception as exc:
            logger.warning("Falha ao logar ciclo: %s", exc)

    logger.info(
        "Ciclo concluído em %.1fs — %s",
        duration, "DRY-RUN" if dry_run else "APLICADO",
    )
    return cycle_data


def _cycle_result(
    config: CuradorConfig,
    preset: Any,
    start: float,
    posts: list,
    dry_run: bool,
    success: bool,
) -> dict[str, Any]:
    """Monta resultado de ciclo para casos de erro/aborto."""

    return {
        "cycle_id": None,
        "timestamp": datetime.now(BST).isoformat(),
        "preset": preset.name,
        "posts_scanned": len(posts),
        "posts_scored": 0,
        "macrotemas_detected": 0,
        "blocks_total": 0,
        "method": "NONE",
        "changes": {},
        "duration_seconds": round(time.monotonic() - start, 2),
        "success": success,
        "dry_run": dry_run,
    }


async def main() -> None:
    """Entrypoint principal — modo contínuo ou execução única."""

    parser = argparse.ArgumentParser(
        description="Curador V4 — Editor-Chefe Algorítmico TIER 1",
    )
    parser.add_argument("--dry-run", action="store_true", help="Não aplicar mudanças no WordPress")
    parser.add_argument("--once", action="store_true", help="Executar apenas um ciclo e sair")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    config = load_config()
    wp_client = _create_wp_client(config)
    redis_client = aioredis.from_url(config.redis_url, decode_responses=True)

    try:
        if args.once:
            # Modo execução única
            if not await _acquire_lock(redis_client):
                logger.warning("Outro ciclo em execução — abortando")
                return
            try:
                result = await run_cycle(config, wp_client, redis_client, dry_run=args.dry_run)
                logger.info("Resultado: %s", json.dumps(result, ensure_ascii=False, default=str))
            finally:
                await _release_lock(redis_client)
        else:
            # Modo contínuo
            logger.info("Curador V4 iniciado em modo contínuo")
            while True:
                preset = get_current_preset()
                interval = {
                    "matinal": config.cycle_interval_normal,
                    "horario_nobre": config.cycle_interval_nobre,
                    "vespertino": config.cycle_interval_normal,
                    "noturno": config.cycle_interval_noturno,
                }[preset.name]

                if await _acquire_lock(redis_client):
                    try:
                        await run_cycle(config, wp_client, redis_client, dry_run=args.dry_run)
                    except Exception as exc:
                        logger.error("Erro no ciclo: %s", exc, exc_info=True)
                    finally:
                        await _release_lock(redis_client)
                else:
                    logger.debug("Lock ativo — pulando ciclo")

                logger.info("Próximo ciclo em %ds (preset: %s)", interval, preset.name)
                await asyncio.sleep(interval)
    finally:
        await wp_client.close()
        await redis_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
