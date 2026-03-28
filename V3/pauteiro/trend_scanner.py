"""Scanner de sinais para o Pauteiro."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from .schemas import TrendSignal

logger = logging.getLogger(__name__)


class TrendScanner:
    """Normaliza sinais coletados de múltiplas entradas externas."""

    async def scan(self, raw_signals: list[dict]) -> list[TrendSignal]:
        """Converte sinais brutos em schema estrito."""

        parsed: list[TrendSignal] = []
        for item in raw_signals:
            try:
                parsed.append(
                    TrendSignal(
                        signal_id=str(item.get("signal_id") or item.get("id") or item.get("url") or item.get("titulo", "")).strip(),
                        titulo=str(item.get("titulo", "")).strip(),
                        resumo=str(item.get("resumo", "")).strip(),
                        editoria=str(item.get("editoria", "ultimas_noticias")).strip() or "ultimas_noticias",
                        fonte=str(item.get("fonte", "desconhecida")).strip() or "desconhecida",
                        score=float(item.get("score", 0.5)),
                        url=item.get("url"),
                        coletado_em=item.get("coletado_em") or datetime.now(timezone.utc),
                    )
                )
            except Exception:
                logger.exception("Falha ao normalizar sinal")
        return parsed
