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
COOLDOWN_THRESHOLD = 0.0


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
            redis_score_key = f"health:{record.provider}:{record.model}:score"
            redis_calls_key = f"health:{record.provider}:{record.model}:calls"
            redis_cool_key = f"health:{record.provider}:{record.model}:cooldown"
            await self.redis.set(redis_score_key, str(score), ex=3600)
            await self.redis.rpush(
                redis_calls_key,
                json.dumps(
                    {
                        "success": record.success,
                        "latency_ms": record.latency_ms,
                        "timestamp": record.timestamp.isoformat(),
                        "error_type": record.error_type,
                    }
                ),
            )
            await self.redis.ltrim(redis_calls_key, -HEALTH_WINDOW_SIZE, -1)
            await self.redis.expire(redis_calls_key, 3600)
            if score <= COOLDOWN_THRESHOLD:
                await self.redis.set(redis_cool_key, "1", ex=300)
            else:
                await self.redis.delete(redis_cool_key)
        return score

    async def get_health_score(self, provider: str, model: str) -> float:
        """Retorna score atual ou default neutro."""

        key = self._key(provider, model)
        if self.redis is not None:
            raw = await self.redis.get(f"health:{provider}:{model}:score")
            if raw is not None:
                return float(raw)
        if key not in self._calls or not self._calls[key]:
            return 70.0
        return self._calculate_score(list(self._calls[key]))

    async def is_in_cooldown(self, provider: str, model: str) -> bool:
        """Informa se modelo está em cooldown."""

        key = self._key(provider, model)
        if self.redis is not None:
            return bool(await self.redis.exists(f"health:{provider}:{model}:cooldown"))
        return key in self._cooldown

    def _calculate_score(self, records: list[CallRecord]) -> float:
        """Calcula score composto: sucesso, latência e recência de erro."""

        if not records:
            return 70.0

        total = len(records)
        successes = [record for record in records if record.success]
        success_rate = len(successes) / total
        success_score = success_rate * 50.0

        avg_latency_s = mean(record.latency_ms for record in successes) / 1000 if successes else 30
        latency_factor = 1.0 - min(avg_latency_s / 30.0, 1.0)
        latency_score = latency_factor * 30.0

        failed = [record for record in records if not record.success]
        if not failed:
            recency_score = 20.0
        else:
            last_error = max(record.timestamp for record in failed)
            seconds_since = (
                datetime.now(timezone.utc) - last_error.replace(tzinfo=timezone.utc)
            ).total_seconds()
            recency_score = min(seconds_since / 300.0, 1.0) * 20.0

        score = max(0.0, min(100.0, success_score + latency_score + recency_score))
        return score
