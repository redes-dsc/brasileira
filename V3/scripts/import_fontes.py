#!/usr/bin/env python3
"""Importa fontes do Supabase (catalogo_fontes) para PostgreSQL Docker."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import asyncpg
import httpx
from dotenv import load_dotenv

SUPABASE_URL = "https://rigjupativtltogrmlun.supabase.co"
CATALOGO_PATH = "/rest/v1/catalogo_fontes"
DEFAULT_PG_DSN = "postgresql://brasileira:brasileira@postgres:5432/brasileira_v3"

V3_ROOT = Path(__file__).resolve().parent.parent
logger = logging.getLogger(__name__)


def _load_env() -> None:
    load_dotenv(V3_ROOT / ".env")
    load_dotenv()


def _parse_ts(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _ultimo_erro_param(val: Any) -> datetime | str | None:
    """Compatível com ultimo_erro TIMESTAMP ou TEXT conforme o schema aplicado."""
    if val is None:
        return None
    if isinstance(val, str) and not val.strip():
        return None
    parsed = _parse_ts(val)
    if parsed is not None:
        return parsed
    if isinstance(val, str):
        return val
    return str(val)


def _tier_from_peso(peso: Any) -> str:
    try:
        p = int(peso) if peso is not None else 0
    except (TypeError, ValueError):
        p = 0
    if p >= 8:
        return "vip"
    if p >= 5:
        return "padrao"
    return "secundario"


def _normalize_tipo(raw: Any) -> str:
    if raw is None:
        return "rss"
    t = str(raw).lower().strip()
    if t in ("scraper", "rss"):
        return t
    return "rss"


def _config_scraper(seletores: Any) -> dict[str, Any]:
    if seletores is None:
        return {}
    if isinstance(seletores, dict):
        return seletores
    if isinstance(seletores, str):
        try:
            out = json.loads(seletores)
            return out if isinstance(out, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _polling_interval_min(intervalo_polling: Any) -> int:
    if intervalo_polling is None:
        return 30
    try:
        sec = int(intervalo_polling)
    except (TypeError, ValueError):
        return 30
    if sec <= 0:
        return 30
    return max(1, sec // 60)


def _as_bool_ativa(raw: Any) -> bool:
    if raw is None:
        return True
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    s = str(raw).lower().strip()
    return s in ("1", "true", "t", "yes", "y", "on", "ativo", "ativa")


def map_row(row: dict[str, Any], ultimo_erro_timestamp: bool) -> tuple[Any, ...] | None:
    fid = row.get("id")
    nome = row.get("nome")
    url = row.get("url")
    if fid is None or nome is None or url is None:
        logger.warning("Linha ignorada (falta id, nome ou url): %s", row.get("id"))
        return None
    raw_erro = row.get("ultimo_erro")
    if ultimo_erro_timestamp:
        ue: datetime | str | None = _parse_ts(raw_erro)
    else:
        ue = _ultimo_erro_param(raw_erro)
    return (
        int(fid),
        str(nome).strip() or "(sem nome)",
        str(url).strip(),
        _normalize_tipo(row.get("tipo")),
        _tier_from_peso(row.get("peso")),
        _config_scraper(row.get("seletores")),
        _polling_interval_min(row.get("intervalo_polling")),
        _parse_ts(row.get("ultimo_sucesso")),
        ue,
        _as_bool_ativa(row.get("ativo")),
    )


UPSERT_SQL = """
INSERT INTO fontes (
    id, nome, url, tipo, tier, config_scraper, polling_interval_min,
    ultimo_sucesso, ultimo_erro, ativa
) VALUES (
    $1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10
)
ON CONFLICT (id) DO UPDATE SET
    nome = EXCLUDED.nome,
    url = EXCLUDED.url,
    tipo = EXCLUDED.tipo,
    tier = EXCLUDED.tier,
    config_scraper = EXCLUDED.config_scraper,
    polling_interval_min = EXCLUDED.polling_interval_min,
    ultimo_sucesso = EXCLUDED.ultimo_sucesso,
    ultimo_erro = EXCLUDED.ultimo_erro,
    ativa = EXCLUDED.ativa
"""


async def fetch_catalogo_fontes(client: httpx.AsyncClient, anon_key: str) -> list[dict[str, Any]]:
    headers = {
        "apikey": anon_key,
        "Authorization": f"Bearer {anon_key}",
        "Accept": "application/json",
    }
    all_rows: list[dict[str, Any]] = []
    page_size = 1000
    start = 0
    while True:
        range_hdr = f"{start}-{start + page_size - 1}"
        r = await client.get(
            f"{SUPABASE_URL}{CATALOGO_PATH}",
            params={"select": "*"},
            headers={**headers, "Range": range_hdr},
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        all_rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return all_rows


async def _ultimo_erro_is_timestamp(conn: asyncpg.Connection) -> bool:
    dt = await conn.fetchval(
        """
        SELECT data_type FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'fontes' AND column_name = 'ultimo_erro'
        """
    )
    if not dt:
        return True
    return str(dt).lower().startswith("timestamp")


async def import_fontes(anon_key: str, pg_dsn: str) -> int:
    async with httpx.AsyncClient(timeout=120.0) as client:
        rows = await fetch_catalogo_fontes(client, anon_key)
    logger.info("Recebidas %d linhas do Supabase", len(rows))

    conn = await asyncpg.connect(pg_dsn)
    try:
        ue_ts = await _ultimo_erro_is_timestamp(conn)
        inserted = 0
        async with conn.transaction():
            for row in rows:
                mapped = map_row(row, ultimo_erro_timestamp=ue_ts)
                if mapped is None:
                    continue
                await conn.execute(UPSERT_SQL, *mapped)
                inserted += 1
        await conn.execute(
            "SELECT setval(pg_get_serial_sequence('fontes', 'id'), "
            "(SELECT COALESCE(MAX(id), 1) FROM fontes))"
        )
    finally:
        await conn.close()
    return inserted


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    _load_env()

    parser = argparse.ArgumentParser(description="Importa catalogo_fontes do Supabase para PostgreSQL.")
    parser.add_argument(
        "anon_key",
        nargs="?",
        default=None,
        help="Supabase anon key (opcional se SUPABASE_ANON_KEY estiver no .env)",
    )
    parser.add_argument(
        "--dsn",
        default=os.environ.get("POSTGRES_DSN") or os.environ.get("PG_DSN") or DEFAULT_PG_DSN,
        help=f"DSN asyncpg (default: {DEFAULT_PG_DSN!r} ou POSTGRES_DSN / PG_DSN)",
    )
    args = parser.parse_args()

    key = args.anon_key or os.environ.get("SUPABASE_ANON_KEY")
    if not key:
        logger.error(
            "Defina SUPABASE_ANON_KEY no .env (%s) ou passe a chave como argumento.",
            V3_ROOT / ".env",
        )
        return 1

    try:
        n = asyncio.run(import_fontes(key.strip(), args.dsn))
    except httpx.HTTPStatusError as e:
        logger.error("HTTP %s: %s", e.response.status_code, e.response.text[:500])
        return 1
    except Exception:
        logger.exception("Falha na importação")
        return 1

    logger.info("Importação concluída: %d fontes aplicadas (upsert por id).", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
