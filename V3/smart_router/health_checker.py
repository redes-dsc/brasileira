"""Health scoring dinâmico por modelo."""

from __future__ import annotations

import json
import logging
from collections import defaultdict, deque
from datetime import datetime, timezone
from statistics import mean

from shared.schemas import CallRecord

logger = logging.getLogger(__name__)

HEALTH_WINDOW_SIZE = 20
DEPRIORITIZE_THRESHOLD = 30.0
COOLDOWN_THRESHOLD = 10.0
COOLDOWN_TTL_SECONDS = 300


class ProviderHealthChecker:
    """Rastreia score (0-100) por modelo."""

    def __init__(self, redis_client=None):
        self.redis = redis_client
        self._calls: dict[str, deque[CallRecord]] = defaultdict(
            lambda: deque(maxlen=HEALTH_WINDOW_SIZE)
        )
        self._cooldown: dict[str, datetime] = {}

    def _key(self, provider: str, model: str) -> str:
        return f"{provider}:{model}"

    async def record_call(self, record: CallRecord) -> float:
        """Registra chamada e retorna score recalculado."""
        key = self._key(record.provider, record.model)
        self._calls[key].append(record)
        score = self._calculate_score(list(self._calls[key]))
        if score <= COOLDOWN_THRESHOLD:
            self._cooldown[key] = datetime.now(timezone.utc)

        if self.redis is not None:
            try:
                redis_score_key = f"health:{record.provider}:{record.model}:score"
                redis_calls_key = f"health:{record.provider}:{record.model}:calls"
                redis_cool_key = f"health:{record.provider}:{record.model}:cooldown"
                pipe = self.redis.pipeline()
                pipe.set(redis_score_key, str(score), ex=3600)
                pipe.rpush(redis_calls_key, json.dumps({
                    "success": record.success,
                    "latency_ms": record.latency_ms,
                    "timestamp": record.timestamp.isoformat(),
                    "error_type": record.error_type,
                }))
                pipe.ltrim(redis_calls_key, -HEALTH_WINDOW_SIZE, -1)
                pipe.expire(redis_calls_key, 3600)
                if score <= COOLDOWN_THRESHOLD:
                    pipe.set(redis_cool_key, "1", ex=COOLDOWN_TTL_SECONDS)
                else:
                    pipe.delete(redis_cool_key)
                await pipe.execute()
            except Exception:
                logger.debug("Falha ao persistir health em Redis", exc_info=True)
        return score

    async def get_health_score(self, provider: str, model: str) -> float:
        """Retorna score atual ou default neutro."""
        key = self._key(provider, model)
        if self.redis is not None:
            try:
                raw = await self.redis.get(f"health:{provider}:{model}:score")
                if raw is not None:
                    return float(raw)
            except Exception:
                pass
        if key not in self._calls or not self._calls[key]:
            return 70.0
        return self._calculate_score(list(self._calls[key]))

    async def is_in_cooldown(self, provider: str, model: str) -> bool:
        """Informa se modelo está em cooldown."""
        key = self._key(provider, model)
        if self.redis is not None:
            try:
                return bool(await self.redis.exists(f"health:{provider}:{model}:cooldown"))
            except Exception:
                pass
        return key in self._cooldown

    def _calculate_score(self, records: list[CallRecord]) -> float:
        """Calcula score composto: 50% sucesso, 30% latência, 20% recência de erro."""
        if not records:
            return 70.0

        total = len(records)
        successes = [r for r in records if r.success]
        success_rate = len(successes) / total
        success_score = success_rate * 50.0

        avg_latency_s = mean(r.latency_ms for r in successes) / 1000 if successes else 30
        latency_factor = 1.0 - min(avg_latency_s / 30.0, 1.0)
        latency_score = latency_factor * 30.0

        failed = [r for r in records if not r.success]
        if not failed:
            recency_score = 20.0
        else:
            last_error = max(r.timestamp for r in failed)
            # Ensure timezone-aware
            if last_error.tzinfo is None:
                last_error = last_error.replace(tzinfo=timezone.utc)
            seconds_since = (datetime.now(timezone.utc) - last_error).total_seconds()
            recency_score = min(seconds_since / 300.0, 1.0) * 20.0

        return max(0.0, min(100.0, success_score + latency_score + recency_score))
