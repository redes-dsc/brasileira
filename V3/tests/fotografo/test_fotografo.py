from __future__ import annotations

import pytest

from fotografo.clip_validator import CLIPValidator
from fotografo.fotografo import FotografoAgent
from fotografo.query_generator import QueryGenerator
from fotografo.tier1_original import Tier1Original
from fotografo.tier4_placeholder import Tier4Placeholder


@pytest.mark.asyncio
async def test_tier1_extraction():
    extractor = Tier1Original()
    html = '<html><head><meta property="og:image" content="https://img.example.com/a.jpg"></head></html>'
    result = await extractor.extract("https://fonte.example.com", html)
    assert result["success"] is True
    assert result["candidate"]["url"].endswith("a.jpg")


def test_tier4_placeholder_default():
    tier4 = Tier4Placeholder()
    candidate = tier4.get_placeholder("categoria_inexistente")
    assert candidate["source_api"] == "placeholder"
    assert candidate["wp_media_id"] == 7999


@pytest.mark.asyncio
async def test_clip_validator_score_range():
    validator = CLIPValidator()
    score = await validator.score("https://images.example.com/politica-brasil.jpg", "Política no Brasil")
    assert 0.0 <= score <= 1.0


@pytest.mark.asyncio
async def test_query_generator_fallback():
    class DummyRouter:
        async def route_request(self, request):
            class R:
                content = "not-json"

            return R()

    generator = QueryGenerator(DummyRouter())
    data = await generator.generate("Título", "Conteúdo", "politica", "https://fonte")
    assert "tier1" in data
    assert len(data["tier2"]) > 0


@pytest.mark.asyncio
async def test_agent_pipeline_success_tier1():
    class DummyRouter:
        async def route_request(self, request):
            class TierObj:
                value = "premium"

            class R:
                content = '{"tier1":["query a"],"tier2":["query b"],"tier3":["query c"],"fallback_pt":["fallback"]}'
                provider = "openai"
                model = "gpt-5.4"
                tokens_in = 10
                tokens_out = 20
                tier_used = TierObj()

            return R()

    class DummyWP:
        async def upload_and_attach(self, image_url, post_id, article_title, attribution, wp_media_id=None):
            return True, wp_media_id or 9001

    agent = FotografoAgent(router=DummyRouter(), wp_uploader=DummyWP())
    event = await agent.process_event(
        {
            "post_id": 123,
            "article_id": "abc",
            "titulo": "Título de teste",
            "lead": "Lead de teste",
            "editoria": "politica",
            "url_fonte": "https://fonte.example.com/noticia",
            "html_fonte": '<meta property="og:image" content="https://img.example.com/politica.jpg">',
        }
    )
    assert event.post_id == 123
    assert event.media_id is not None
    assert event.tier_used in {"tier1", "tier2", "tier3", "tier4"}
