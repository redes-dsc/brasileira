"""Schemas Pydantic do Pauteiro."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TrendSignal(BaseModel):
    """Sinal de tendência observado pelo Pauteiro."""

    model_config = ConfigDict(strict=True)

    signal_id: str
    titulo: str
    resumo: str
    editoria: str
    fonte: str
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    url: str | None = None
    coletado_em: datetime


class PautaEspecial(BaseModel):
    """Pauta especial publicada para o pipeline editorial."""

    model_config = ConfigDict(strict=True)

    pauta_id: str
    editoria: str
    titulo: str
    briefing: str
    sinais_ids: list[str]
    prioridade: str = "normal"
    criado_em: datetime
