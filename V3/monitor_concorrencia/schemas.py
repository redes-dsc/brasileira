"""Schemas do monitor de concorrência."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PortalArticle(BaseModel):
    """Item coletado de portal concorrente."""

    model_config = ConfigDict(strict=True)

    portal: str
    titulo: str
    url: str
    coletado_em: datetime


class CoverageResult(BaseModel):
    """Resultado da comparação de cobertura."""

    model_config = ConfigDict(strict=True)

    titulo: str
    status: str
    similaridade: float = Field(ge=0.0, le=1.0)
    topico_destino: str
    topico_normalizado: str
