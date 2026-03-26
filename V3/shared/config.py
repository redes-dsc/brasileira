"""Configurações centralizadas via ambiente/.env."""

from __future__ import annotations

import os
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AppConfig(BaseModel):
    """Configuração principal da aplicação."""

    model_config = ConfigDict(strict=True)

    kafka_bootstrap_servers: str = "localhost:9092"
    redis_url: str = "redis://localhost:6379/0"
    postgres_dsn: str = "postgresql://brasileira:password@localhost:5432/brasileira_v3"

    wp_url: str = "https://brasileira.news"
    wp_user: str = "iapublicador"
    wp_auth: str = ""

    ingestion_num_workers: int = Field(default=30, ge=1)
    ingestion_cycle_interval: int = Field(default=1800, ge=60)

    llm_timeout: int = Field(default=30, ge=1)


def load_keys(prefix: str) -> list[str]:
    """Carrega KEY, KEY_2...KEY_9 para rotação."""

    keys: list[str] = []
    base = os.getenv(prefix, "").strip()
    if base:
        keys.append(base)
    for idx in range(2, 10):
        key = os.getenv(f"{prefix}_{idx}", "").strip()
        if key:
            keys.append(key)
    return keys


def load_config(env_path: Optional[str] = None) -> AppConfig:
    """Carrega configuração do ambiente e valida via Pydantic."""

    if env_path:
        try:
            from dotenv import load_dotenv
        except ModuleNotFoundError as exc:
            raise RuntimeError("python-dotenv não está instalado") from exc

        load_dotenv(env_path)

    return AppConfig(
        kafka_bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        postgres_dsn=os.getenv(
            "POSTGRES_DSN", "postgresql://brasileira:password@localhost:5432/brasileira_v3"
        ),
        wp_url=os.getenv("WP_URL", "https://brasileira.news"),
        wp_user=os.getenv("WP_USER", "iapublicador"),
        wp_auth=os.getenv("WP_AUTH", ""),
        ingestion_num_workers=int(os.getenv("INGESTION_NUM_WORKERS", "30")),
        ingestion_cycle_interval=int(os.getenv("INGESTION_CYCLE_INTERVAL", "1800")),
        llm_timeout=int(os.getenv("LLM_TIMEOUT", "30")),
    )
