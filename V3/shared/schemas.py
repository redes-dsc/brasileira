"""Schemas compartilhados com Pydantic V2 strict mode."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
    timestamp: datetime = Field(default_factory=_utcnow)


class SourceAssignment(BaseModel):
    """Mensagem do tópico fonte-assignments."""
    model_config = ConfigDict(strict=True)
    fonte_id: int
    nome: str
    url: str
    tipo: str
    tier: str
    grupo: str = "geral"
    config_scraper: Optional[dict[str, Any]] = None
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
    conteudo_html: Optional[str] = None
    og_image: Optional[str] = None
    fonte_id: int
    fonte_nome: str
    fonte_tier: str = "padrao"
    grupo: str = "geral"
    tipo_coleta: str
    coletado_em: str
    near_duplicate: bool = False
    near_duplicate_of: Optional[str] = None


class ClassifiedArticle(BaseModel):
    """Mensagem produzida em classified-articles."""
    model_config = ConfigDict(strict=True)
    titulo: str
    url: str
    url_hash: str
    data_publicacao: Optional[str] = None
    resumo: str = ""
    conteudo_html: Optional[str] = None
    og_image: Optional[str] = None
    fonte_id: int
    fonte_nome: str
    fonte_tier: str = "padrao"
    grupo: str = "geral"
    tipo_coleta: str
    coletado_em: str
    editoria: str
    categoria_wp_id: int
    relevancia_score: float
    urgencia: str = "NORMAL"
    entidades: dict[str, list[str]] = Field(default_factory=dict)
    confianca_classificacao: float = 0.0


class PublishedArticle(BaseModel):
    """Mensagem produzida em article-published."""
    model_config = ConfigDict(strict=True)
    wp_post_id: int
    titulo: str
    resumo: str = ""
    url_fonte: str
    url_hash: str
    editoria: str
    categoria_wp_id: int
    relevancia_score: float = 0.0
    urgencia: str = "NORMAL"
    fonte_id: int
    fonte_nome: str
    conteudo_html: Optional[str] = None
    og_image: Optional[str] = None
    publicado_em: str
