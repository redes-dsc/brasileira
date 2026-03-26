"""SmartLLMRouter com fallback em cascata e health-aware routing."""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable, Optional

from shared.schemas import CallRecord, LLMRequest, LLMResponse, ModelPoolEntry, TierName

from .cost_tracker import estimate_cost_usd
from .health_checker import DEPRIORITIZE_THRESHOLD, ProviderHealthChecker
from .tier_manager import DEFAULT_TIER_POOLS, normalize_pool, resolve_tier, tiers_from

logger = logging.getLogger(__name__)


class LLMRouterError(Exception):
    """Erro base do roteador."""


class AllProvidersFailedError(LLMRouterError):
    """Todos os providers falharam em todos os tiers."""

    def __init__(self, task_type: str, tiers_attempted: list[str], errors: list[dict[str, str]]):
        self.task_type = task_type
        self.tiers_attempted = tiers_attempted
        self.errors = errors
        super().__init__(
            f"Todos os provedores falharam para {task_type}. "
            f"Tiers tentados: {tiers_attempted}. Total de erros: {len(errors)}"
        )


class NoKeysConfiguredError(LLMRouterError):
    """Nenhuma key para o provedor solicitado."""


class SmartLLMRouter:
    """Roteador inteligente de chamadas LLM."""

    def __init__(
        self,
        redis_client=None,
        provider_keys: Optional[dict[str, list[str]]] = None,
        pg_pool=None,
        completion_fn: Optional[Callable[..., Any]] = None,
    ):
        self.redis = redis_client
        self.pg_pool = pg_pool
        self.provider_keys = provider_keys or {}
        self.key_indexes: dict[str, int] = defaultdict(int)
        self.health_tracker = ProviderHealthChecker(redis_client=redis_client)
        self.completion_fn = completion_fn

    def _resolve_tier(self, task_type: str) -> str:
        return resolve_tier(task_type)

    async def _load_tier_pool(self, tier: str) -> list[ModelPoolEntry]:
        if self.redis is not None:
            redis_key = f"llm:tier_pools:{tier}"
            raw = await self.redis.get(redis_key)
            if raw:
                payload = json.loads(raw)
                return normalize_pool(payload)
        return normalize_pool(DEFAULT_TIER_POOLS[tier])

    async def update_tier_pool(self, tier: str, entries: list[dict[str, object]]) -> None:
        """Atualiza pool de tier em runtime no Redis."""

        normalized = [entry.model_dump() for entry in normalize_pool(entries)]
        if self.redis is None:
            raise RuntimeError("Redis indisponível para update de pool")
        await self.redis.set(f"llm:tier_pools:{tier}", json.dumps(normalized), ex=86400)

    def _next_key(self, provider: str) -> str:
        keys = self.provider_keys.get(provider, [])
        if not keys:
            raise NoKeysConfiguredError(f"Sem keys para provider: {provider}")
        idx = self.key_indexes[provider] % len(keys)
        self.key_indexes[provider] += 1
        return keys[idx]

    def _model_name(self, provider: str, model: str) -> str:
        prefix_map = {
            "anthropic": "anthropic",
            "openai": "openai",
            "google": "gemini",
            "xai": "xai",
            "perplexity": "perplexity",
            "deepseek": "deepseek",
            "alibaba": "openai",
        }
        return f"{prefix_map.get(provider, provider)}/{model}"

    async def _ordered_pool(self, tier: str) -> list[ModelPoolEntry]:
        entries = await self._load_tier_pool(tier)
        scored: list[tuple[float, ModelPoolEntry]] = []
        for entry in entries:
            score = await self.health_tracker.get_health_score(entry.provider, entry.model)
            effective = score * entry.weight
            if score < DEPRIORITIZE_THRESHOLD:
                effective *= 0.1
            scored.append((effective, entry))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [entry for _, entry in scored]

    async def _call_llm(self, model_name: str, api_key: str, request: LLMRequest) -> Any:
        completion = self.completion_fn
        if completion is None:
            from litellm import acompletion

            completion = acompletion
        return await completion(
            model=model_name,
            messages=request.messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            response_format=request.response_format,
            timeout=request.timeout,
            api_key=api_key,
        )

    async def _log_health(self, record: CallRecord) -> None:
        await self.health_tracker.record_call(record)
        if self.pg_pool is None:
            return
        async with self.pg_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO llm_health_log (
                    provider, model, success, latency_ms, tokens_in, tokens_out, cost_usd,
                    error_type, error_message, task_type, tier, timestamp
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                """,
                record.provider,
                record.model,
                record.success,
                record.latency_ms,
                record.tokens_in,
                record.tokens_out,
                record.cost_usd,
                record.error_type,
                record.error_message,
                record.task_type,
                record.tier,
                record.timestamp,
            )

    async def route_request(self, request: LLMRequest) -> LLMResponse:
        """Roteia request com fallback cross-tier e health scoring."""

        requested_tier = self._resolve_tier(request.task_type)
        attempted_tiers: list[str] = []
        errors: list[dict[str, str]] = []

        for tier in tiers_from(requested_tier):
            attempted_tiers.append(tier)
            pool = await self._ordered_pool(tier)

            for entry in pool:
                if await self.health_tracker.is_in_cooldown(entry.provider, entry.model):
                    continue

                try:
                    api_key = self._next_key(entry.provider)
                except NoKeysConfiguredError as exc:
                    errors.append(
                        {"tier": tier, "provider": entry.provider, "model": entry.model, "error": str(exc)}
                    )
                    continue

                start = time.perf_counter()
                try:
                    raw_response = await self._call_llm(
                        model_name=self._model_name(entry.provider, entry.model),
                        api_key=api_key,
                        request=request,
                    )
                    latency_ms = int((time.perf_counter() - start) * 1000)

                    content = (
                        raw_response.choices[0].message.content
                        if hasattr(raw_response, "choices")
                        else raw_response["choices"][0]["message"]["content"]
                    )
                    usage = getattr(raw_response, "usage", None)
                    if usage is None and isinstance(raw_response, dict):
                        usage = raw_response.get("usage")

                    tokens_in = getattr(usage, "prompt_tokens", None) if usage is not None else None
                    if tokens_in is None and isinstance(usage, dict):
                        tokens_in = usage.get("prompt_tokens")
                    tokens_out = getattr(usage, "completion_tokens", None) if usage is not None else None
                    if tokens_out is None and isinstance(usage, dict):
                        tokens_out = usage.get("completion_tokens")

                    cost = estimate_cost_usd(entry.model, tokens_in, tokens_out)
                    record = CallRecord(
                        provider=entry.provider,
                        model=entry.model,
                        success=True,
                        latency_ms=latency_ms,
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        cost_usd=cost,
                        task_type=request.task_type,
                        tier=tier,
                        timestamp=datetime.utcnow(),
                    )
                    await self._log_health(record)

                    return LLMResponse(
                        content=content,
                        provider=entry.provider,
                        model=entry.model,
                        tier_used=TierName(tier),
                        tier_requested=TierName(requested_tier),
                        downgraded=(tier != requested_tier),
                        latency_ms=latency_ms,
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        cost_usd=cost,
                        trace_id=request.trace_id,
                    )
                except Exception as exc:
                    latency_ms = int((time.perf_counter() - start) * 1000)
                    error_type = type(exc).__name__.lower()
                    errors.append(
                        {
                            "tier": tier,
                            "provider": entry.provider,
                            "model": entry.model,
                            "error": str(exc),
                        }
                    )
                    record = CallRecord(
                        provider=entry.provider,
                        model=entry.model,
                        success=False,
                        latency_ms=latency_ms,
                        error_type=error_type,
                        error_message=str(exc),
                        task_type=request.task_type,
                        tier=tier,
                        timestamp=datetime.utcnow(),
                    )
                    await self._log_health(record)
                    continue

        raise AllProvidersFailedError(request.task_type, attempted_tiers, errors)

    async def route_request_safe(self, request: LLMRequest) -> Optional[LLMResponse]:
        """Wrapper seguro que retorna None em falha total."""

        try:
            return await self.route_request(request)
        except AllProvidersFailedError:
            logger.error("Falha total em route_request_safe para task=%s", request.task_type)
            return None

    async def get_health_dashboard(self) -> dict[str, object]:
        """Retorna visão resumida de health por modelo e providers."""

        models: dict[str, dict[str, object]] = {}
        for tier in ("premium", "padrao", "economico"):
            for entry in await self._load_tier_pool(tier):
                key = f"{entry.provider}/{entry.model}"
                score = await self.health_tracker.get_health_score(entry.provider, entry.model)
                cooldown = await self.health_tracker.is_in_cooldown(entry.provider, entry.model)
                models[key] = {
                    "score": round(score, 2),
                    "cooldown": cooldown,
                    "deprioritized": score < DEPRIORITIZE_THRESHOLD,
                }

        providers = {
            provider: {
                "total_keys": len(keys),
                "available_keys": len(keys),
                "enabled": len(keys) > 0,
            }
            for provider, keys in self.provider_keys.items()
        }

        return {"models": models, "providers": providers}
