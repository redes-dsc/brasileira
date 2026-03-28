"""Configurações do Pauteiro."""

from pydantic import BaseModel, ConfigDict, Field


class PauteiroConfig(BaseModel):
    """Configuração estrita do ciclo de pauta especial."""

    model_config = ConfigDict(strict=True)

    kafka_topic_pautas: str = "pautas-especiais"
    cycle_interval_seconds: int = Field(default=300, ge=30)
    dedup_ttl_seconds: int = Field(default=3600, ge=60)
    max_signals_per_cycle: int = Field(default=120, ge=1)
