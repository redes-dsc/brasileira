"""Configuração do monitor de sistema."""

from pydantic import BaseModel, ConfigDict, Field

from editor_chefe.config import MACROCATEGORIAS_16


class MonitorSistemaConfig(BaseModel):
    """Parâmetros de monitoramento e SLO."""

    model_config = ConfigDict(strict=True)

    target_per_hour: int = Field(default=40, ge=1)
    alert_per_hour: int = Field(default=20, ge=1)
    critical_per_hour: int = Field(default=5, ge=1)
    max_polling_minutes: int = Field(default=24 * 60, ge=60)
    min_polling_minutes: int = Field(default=5, ge=1)
    categorias: list[str] = MACROCATEGORIAS_16
