import asyncio

from newsroom_v3.llm.smart_router import SmartLLMRouter


class DummyClient:
    async def complete(self, provider: str, model: str, prompt: str, timeout: int = 30) -> str:
        if provider in {'anthropic', 'openai'}:
            raise RuntimeError('simulated provider error')
        return f"ok:{provider}:{model}"


def test_router_fallback_between_providers() -> None:
    router = SmartLLMRouter(client=DummyClient())
    result = asyncio.run(router.route_request('redacao_artigo', 'teste'))
    assert result['tier'] in {'premium', 'padrao', 'economico'}
    assert result['content'].startswith('ok:')
