"""Logger de ciclos do Curador V4 — persiste dados no Supabase."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from curador_v4.config import CuradorConfig

logger = logging.getLogger(__name__)


async def log_cycle(config: CuradorConfig, cycle_data: dict[str, Any]) -> None:
    """Registra dados do ciclo na tabela curador_cycles do Supabase.

    Campos esperados em cycle_data:
      - cycle_id, timestamp, preset, posts_scanned, posts_scored,
      - macrotemas_detected, blocks_total, method, changes,
      - duration_seconds, success, dry_run
    """

    if not config.supabase_url or not config.supabase_key:
        logger.debug("Supabase não configurado — log de ciclo ignorado")
        return

    url = f"{config.supabase_url}/rest/v1/curador_cycles"
    headers = {
        "apikey": config.supabase_key,
        "Authorization": f"Bearer {config.supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, headers=headers, json=cycle_data)
            resp.raise_for_status()
        logger.info("Ciclo %s logado no Supabase", cycle_data.get("cycle_id", "?"))
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Falha HTTP ao logar ciclo no Supabase: %d — %s",
            exc.response.status_code,
            exc.response.text[:200],
        )
    except Exception as exc:
        logger.warning("Falha ao logar ciclo no Supabase: %s", exc)
