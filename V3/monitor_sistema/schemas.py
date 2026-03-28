"""Schemas do monitor de sistema."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ThroughputStatus(BaseModel):
    """Status de throughput global."""

    model_config = ConfigDict(strict=True)

    artigos_por_hora: float = Field(ge=0)
    nivel: str


class CoverageSnapshot(BaseModel):
    """Cobertura por macrocategoria."""

    model_config = ConfigDict(strict=True)

    categoria: str
    volume_24h: int = Field(ge=0)


class FontePollingDecision(BaseModel):
    """Decisão FOCA para polling de fonte."""

    model_config = ConfigDict(strict=True)

    fonte_id: int
    polling_interval_min: int = Field(ge=1)
    tier: str
    ativa: bool = True
    updated_at: datetime
