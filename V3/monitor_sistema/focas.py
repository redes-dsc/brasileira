"""FOCAS: ajuste de frequência preservando fontes ativas."""

from __future__ import annotations

from datetime import datetime, timezone

from .adaptive_polling import AdaptivePolling
from .schemas import FontePollingDecision


class FocasController:
    """Aplica decisões de polling preservando todas as fontes ativas."""

    VALID_TIERS = {"vip", "padrao", "secundario", "experimental"}

    def __init__(self, adaptive_polling: AdaptivePolling):
        self.adaptive = adaptive_polling

    async def decide(self, fonte: dict, throughput_level: str) -> FontePollingDecision:
        tier = str(fonte.get("tier", "secundario"))
        if tier not in self.VALID_TIERS:
            tier = "secundario"

        new_interval = await self.adaptive.adjust(
            current_interval=int(fonte.get("polling_interval_min", 30)),
            throughput_level=throughput_level,
            consecutive_failures=int(fonte.get("consecutive_failures", 0)),
        )
        return FontePollingDecision(
            fonte_id=int(fonte["id"]),
            polling_interval_min=new_interval,
            tier=tier,
            ativa=True,
            updated_at=datetime.now(timezone.utc),
        )
