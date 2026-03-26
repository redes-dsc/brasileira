"""Schemas compartilhados com Pydantic V2 strict."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TierName(str, Enum):
    PREMIUM = "premium"
    PADRAO = "padrao"
    ECONOMICO = "economico"


class ModelPoolEntry(BaseModel):
    """Entrada de modelo por tier."""

    model_config = ConfigDict(strict=True)

    provider: str
    model: str
    weight: float = Field(default=1.0, gt=0)


class LLMRequest(BaseModel):
    """Request de roteamento LLM."""

    model_config = ConfigDict(strict=True)

    task_type: str
    messages: list[dict[str, str]]
    temperature: float = 0.3
    max_tokens: int = 4096
    response_format: Optional[dict[str, str]] = None
    timeout: int = 30
    trace_id: Optional[str] = None


class LLMResponse(BaseModel):
    """Response unificado de chamada LLM."""

    model_config = ConfigDict(strict=True)

    content: str
    provider: str
    model: str
    tier_used: TierName
    tier_requested: TierName
    downgraded: bool = False
    latency_ms: int
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    cost_usd: Optional[float] = None
    trace_id: Optional[str] = None


class CallRecord(BaseModel):
    """Registro de chamada para health tracking."""

    model_config = ConfigDict(strict=True)

    provider: str
    model: str
    success: bool
    latency_ms: int
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    cost_usd: Optional[float] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    task_type: str
    tier: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SourceAssignment(BaseModel):
    """Mensagem do tópico fonte-assignments."""

    model_config = ConfigDict(strict=True)

    fonte_id: int
    nome: str
    url: str
    tipo: str
    tier: str
    config_scraper: Optional[dict] = None
    polling_interval_min: int = 30
    priority: str = "normal"
    scheduled_at: str
    retry: bool = False


class RawArticle(BaseModel):
    """Mensagem produzida em raw-articles."""

    model_config = ConfigDict(strict=True)

    titulo: str
    url: str
    url_hash: str
    data_publicacao: Optional[str] = None
    resumo: str = ""
    og_image: Optional[str] = None
    fonte_id: int
    fonte_nome: str
    grupo: str = "geral"
    tipo_coleta: str
    coletado_em: str
    near_duplicate: bool = False
    near_duplicate_of: Optional[str] = None
