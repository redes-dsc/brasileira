from dataclasses import asdict
from time import perf_counter
from typing import Protocol

from newsroom_v3.llm.health_tracker import ProviderHealthTracker
from newsroom_v3.llm.tier_config import ModelTarget, TIER_POOLS, resolve_tier


class ProviderClient(Protocol):
    async def complete(self, provider: str, model: str, prompt: str, timeout: int = 30) -> str:
        ...


class RoutingError(RuntimeError):
    pass


class SmartLLMRouter:
    def __init__(self, client: ProviderClient) -> None:
        self.client = client
        self.health = ProviderHealthTracker()

    def _rank(self, pool: list[ModelTarget]) -> list[ModelTarget]:
        return sorted(pool, key=lambda m: self.health.calculate_health(f"{m.provider}:{m.model}"), reverse=True)

    async def route_request(self, task_type: str, content: str) -> dict:
        tier = resolve_tier(task_type)
        response = await self._route_tier(tier, content)
        response['task_type'] = task_type
        return response

    async def _route_tier(self, tier: str, content: str) -> dict:
        pool = self._rank(TIER_POOLS[tier])
        for target in pool:
            model_id = f"{target.provider}:{target.model}"
            t0 = perf_counter()
            try:
                text = await self.client.complete(target.provider, target.model, content, timeout=30)
                latency = int((perf_counter() - t0) * 1000)
                self.health.record(model_id, success=True, latency_ms=latency)
                return {
                    'tier': tier,
                    'model': asdict(target),
                    'latency_ms': latency,
                    'content': text,
                }
            except Exception:
                latency = int((perf_counter() - t0) * 1000)
                self.health.record(model_id, success=False, latency_ms=latency)
                continue

        if tier == 'premium':
            return await self._route_tier('padrao', content)
        if tier == 'padrao':
            return await self._route_tier('economico', content)
        raise RoutingError('all providers failed across all tiers')
