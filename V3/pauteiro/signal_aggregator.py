"""Agregação e deduplicação de sinais do Pauteiro."""

from __future__ import annotations

import hashlib
import logging
import unicodedata
from collections import defaultdict

from shared.memory import MemoryManager

from .config import PauteiroConfig
from .schemas import TrendSignal

logger = logging.getLogger(__name__)


class SignalAggregator:
    """Deduplica sinais e organiza por editoria."""

    def __init__(self, config: PauteiroConfig, memory: MemoryManager | None = None):
        self.config = config
        self.memory = memory
        self._local_seen: set[str] = set()

    @staticmethod
    def _normalize(text: str) -> str:
        value = unicodedata.normalize("NFKD", text.lower().strip())
        return "".join(ch for ch in value if not unicodedata.combining(ch))

    def _fingerprint(self, signal: TrendSignal) -> str:
        base = f"{self._normalize(signal.titulo)}|{signal.editoria}|{signal.url or ''}"
        return hashlib.sha256(base.encode("utf-8")).hexdigest()

    async def deduplicate(self, signals: list[TrendSignal], cycle_id: str) -> list[TrendSignal]:
        """Remove sinais repetidos com memória local/Redis/Postgres quando disponível."""

        unique: list[TrendSignal] = []
        for signal in signals:
            fp = self._fingerprint(signal)
            if fp in self._local_seen:
                continue

            redis_seen = False
            if self.memory and self.memory.redis is not None:
                try:
                    redis_seen = bool(await self.memory.redis.sismember("pauteiro:signals:seen", fp))
                except Exception:
                    logger.exception("Erro consultando deduplicação no Redis")

            if redis_seen:
                continue

            self._local_seen.add(fp)
            unique.append(signal)
            if self.memory and self.memory.redis is not None:
                try:
                    await self.memory.redis.sadd("pauteiro:signals:seen", fp)
                    await self.memory.redis.expire("pauteiro:signals:seen", self.config.dedup_ttl_seconds)
                except Exception:
                    logger.exception("Erro persistindo deduplicação no Redis")

        if self.memory is not None:
            try:
                await self.memory.set_working("pauteiro", cycle_id, {"signals": [s.model_dump(mode="json") for s in unique]})
                await self.memory.add_episodic("pauteiro", {"cycle_id": cycle_id, "signals_count": len(unique)})
            except Exception:
                logger.exception("Falha ao persistir memória do pauteiro")

        return unique

    async def group_by_editoria(self, signals: list[TrendSignal]) -> dict[str, list[TrendSignal]]:
        grouped: dict[str, list[TrendSignal]] = defaultdict(list)
        for signal in sorted(signals, key=lambda x: x.score, reverse=True):
            grouped[signal.editoria].append(signal)
        return dict(grouped)
