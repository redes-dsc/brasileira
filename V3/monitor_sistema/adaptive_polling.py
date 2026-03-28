"""Ajuste adaptativo de polling das fontes."""

from __future__ import annotations

from .config import MonitorSistemaConfig


class AdaptivePolling:
    """Calcula novos intervalos preservando fontes ativas."""

    def __init__(self, config: MonitorSistemaConfig):
        self.config = config

    async def adjust(self, current_interval: int, throughput_level: str, consecutive_failures: int = 0) -> int:
        interval = int(current_interval)

        if throughput_level == "critico":
            interval = max(self.config.min_polling_minutes, interval // 2)
        elif throughput_level == "alerta":
            interval = max(self.config.min_polling_minutes, int(interval * 0.8))
        elif throughput_level == "saudavel":
            interval = min(self.config.max_polling_minutes, int(interval * 1.1))

        if consecutive_failures > 0:
            interval = min(self.config.max_polling_minutes, int(interval * min(1 + consecutive_failures * 0.3, 3.0)))

        return min(self.config.max_polling_minutes, max(self.config.min_polling_minutes, interval))
