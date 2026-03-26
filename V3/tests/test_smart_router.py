from __future__ import annotations

from types import SimpleNamespace

import pytest

from shared.schemas import LLMRequest
from smart_router.router import AllProvidersFailedError, SmartLLMRouter


@pytest.fixture
def router() -> SmartLLMRouter:
    provider_keys = {
        "anthropic": ["k1"],
        "openai": ["k2"],
        "google": ["k3"],
        "xai": ["k4"],
        "perplexity": ["k5"],
        "deepseek": ["k6"],
        "alibaba": ["k7"],
    }
    return SmartLLMRouter(redis_client=None, provider_keys=provider_keys)


def test_tier_resolution(router: SmartLLMRouter) -> None:
    assert router._resolve_tier("redacao_artigo") == "premium"
    assert router._resolve_tier("seo_otimizacao") == "padrao"
    assert router._resolve_tier("classificacao_categoria") == "economico"
    assert router._resolve_tier("desconhecida") == "padrao"


@pytest.mark.asyncio
async def test_downgrade_to_padrao(monkeypatch: pytest.MonkeyPatch, router: SmartLLMRouter) -> None:
    calls = {"count": 0}

    async def fake_completion(**kwargs):
        calls["count"] += 1
        # 8 modelos premium no default; depois entra padrao
        if calls["count"] <= 8:
            raise RuntimeError("rate limit")
        return {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        }

    router.completion_fn = fake_completion

    request = LLMRequest(task_type="redacao_artigo", messages=[{"role": "user", "content": "teste"}])
    response = await router.route_request(request)
    assert response.content == "ok"
    assert response.downgraded is True
    assert response.tier_used.value == "padrao"


@pytest.mark.asyncio
async def test_all_providers_fail(router: SmartLLMRouter) -> None:
    async def fake_completion(**kwargs):
        raise RuntimeError("server error")

    router.completion_fn = fake_completion

    request = LLMRequest(task_type="redacao_artigo", messages=[{"role": "user", "content": "teste"}])
    with pytest.raises(AllProvidersFailedError):
        await router.route_request(request)


@pytest.mark.asyncio
async def test_health_defaults(router: SmartLLMRouter) -> None:
    score = await router.health_tracker.get_health_score("openai", "gpt-5.4")
    assert score == 70.0
    assert await router.health_tracker.is_in_cooldown("openai", "gpt-5.4") is False


@pytest.mark.asyncio
async def test_key_rotation(router: SmartLLMRouter) -> None:
    assert router._next_key("anthropic") == "k1"
    with pytest.raises(Exception):
        router._next_key("unknown")


@pytest.mark.asyncio
async def test_dashboard(router: SmartLLMRouter) -> None:
    dashboard = await router.get_health_dashboard()
    assert "models" in dashboard
    assert "providers" in dashboard
    assert dashboard["providers"]["openai"]["enabled"] is True
