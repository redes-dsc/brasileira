"""Schemas do Editor-Chefe."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CategoryMetrics(BaseModel):
    """Métricas de publicação por macrocategoria."""

    model_config = ConfigDict(strict=True)

    categoria: str
    publicados_1h: int = Field(default=0, ge=0)
    publicados_24h: int = Field(default=0, ge=0)
    horas_desde_ultimo: float = Field(default=9999.0, ge=0.0)
    score_cobertura: float = Field(default=0.0, ge=0.0, le=1.0)


class GapSignal(BaseModel):
    """Sinal de gap urgente para pauta-gap."""

    model_config = ConfigDict(strict=True)

    categoria: str
    urgencia: str
    motivo: str
    peso_sugerido: float = Field(ge=0.5, le=2.0)
    criado_em: datetime
