from __future__ import annotations

import pytest

from reporter.content_extractor import extrair_conteudo_fonte
from reporter.reporter import ReporterAgent


@pytest.mark.asyncio
async def test_extracao_fallback_resumo(monkeypatch: pytest.MonkeyPatch):
    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            raise RuntimeError("timeout")

    import reporter.content_extractor as module

    monkeypatch.setattr(module.httpx, "AsyncClient", lambda *args, **kwargs: DummyClient())

    result = await extrair_conteudo_fonte(
        url="https://example.com/article",
        resumo_original="Resumo de teste do artigo.",
    )
    assert result["conteudo"] == "Resumo de teste do artigo."
    assert result["extracao_metodo"] == "fallback_resumo"


@pytest.mark.asyncio
async def test_pipeline_publica(monkeypatch: pytest.MonkeyPatch):
    class DummyRouter:
        async def route_request(self, request):
            class R:
                content = (
                    '{"titulo":"Título final","corpo":"Corpo final","resumo":"Resumo final",'
                    '"title_seo":"SEO","meta_description":"Meta","slug":"titulo-final"}'
                )
                provider = "openai"
                model = "gpt-4.1-mini"
                tokens_in = 10
                tokens_out = 20
                tier_used = type("T", (), {"value": "padrao"})()

            return R()

    class DummyWP:
        async def post(self, endpoint, json=None):
            assert endpoint == "/wp-json/wp/v2/posts"
            assert json["status"] == "publish"
            return {"id": 123}

    agent = ReporterAgent(router=DummyRouter(), wp_client=DummyWP())
    result = await agent.processar(
        {
            "url": "https://example.com",
            "resumo": "Resumo",
            "titulo": "Título",
            "categoria": "politica",
            "categoria_wp_id": 2,
            "wp_tags": [10, 11],
        }
    )
    assert result.publicado is True
    assert result.post_id == 123
