"""Configuração do monitor de concorrência."""

from pydantic import BaseModel, ConfigDict, Field


class MonitorConcorrenciaConfig(BaseModel):
    """Configuração estrita de escaneamento e análise concorrencial."""

    model_config = ConfigDict(strict=True)

    cycle_minutes: int = Field(default=30, ge=1)
    timeout_seconds: int = Field(default=20, ge=5)
    retries: int = Field(default=2, ge=0)
    max_articles_per_portal: int = Field(default=30, ge=1)

    covered_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    partial_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    cluster_similarity_threshold: float = Field(default=0.45, ge=0.0, le=1.0)
    breaking_min_portals: int = Field(default=4, ge=2)

    topic_gap: str = "pautas-gap"
    topic_consolidacao: str = "consolidacao"
    topic_breaking: str = "breaking-candidate"
