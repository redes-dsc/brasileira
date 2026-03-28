"""Health checker operacional do monitor."""

from __future__ import annotations

from .schemas import ThroughputStatus


class HealthChecker:
    """Consolida saúde sistêmica (informativo, não bloqueante)."""

    async def summarize(self, throughput: ThroughputStatus, cost_usd_hour: float | None = None) -> dict[str, str | float | None]:
        return {
            "throughput_nivel": throughput.nivel,
            "custo_usd_hora": cost_usd_hour,
            "blocking": False,
        }
