"""Configuração do Editor-Chefe."""

from pydantic import BaseModel, ConfigDict, Field


MACROCATEGORIAS_16 = [
    "politica", "economia", "esportes", "tecnologia", "saude", "educacao",
    "ciencia", "cultura_entretenimento", "mundo_internacional", "meio_ambiente",
    "seguranca_justica", "sociedade", "brasil", "regionais", "opiniao_analise", "ultimas_noticias",
]


class EditorChefeConfig(BaseModel):
    """Parâmetros analíticos do observer estratégico."""

    model_config = ConfigDict(strict=True)

    kafka_topic_gaps: str = "pautas-gap"
    redis_weight_prefix: str = "editorial:pesos"
    cycle_seconds: int = Field(default=3600, ge=60)
    gap_hours_threshold: float = Field(default=2.0, ge=0.1)
    min_weight: float = Field(default=0.5, ge=0.5, le=2.0)
    max_weight: float = Field(default=2.0, ge=0.5, le=2.0)
