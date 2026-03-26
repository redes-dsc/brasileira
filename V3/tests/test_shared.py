import os

import pytest

from shared.config import load_keys
from shared.schemas import LLMRequest, SourceAssignment, TierName
from shared.wp_client import WordPressClient


def test_load_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k1")
    monkeypatch.setenv("OPENAI_API_KEY_2", "k2")
    monkeypatch.setenv("OPENAI_API_KEY_4", "k4")
    keys = load_keys("OPENAI_API_KEY")
    assert keys == ["k1", "k2", "k4"]


def test_llm_request_schema_strict() -> None:
    request = LLMRequest(task_type="redacao_artigo", messages=[{"role": "user", "content": "oi"}])
    assert request.task_type == "redacao_artigo"


def test_source_assignment_schema() -> None:
    assignment = SourceAssignment(
        fonte_id=1,
        nome="Agência Brasil",
        url="https://example.com/rss",
        tipo="rss",
        tier="vip",
        scheduled_at="2026-03-26T12:00:00Z",
    )
    assert assignment.priority == "normal"


@pytest.mark.asyncio
async def test_wp_client_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    class DummyResponse:
        def __init__(self, code: int):
            self.status_code = code
            self.request = object()
            self.content = b'{"ok": true}' if code == 200 else b""

        def raise_for_status(self):
            if self.status_code >= 400:
                import httpx

                raise httpx.HTTPStatusError("err", request=self.request, response=self)

        def json(self):
            return {"ok": True}

    async def fake_request(*args, **kwargs):
        calls["count"] += 1
        return DummyResponse(429 if calls["count"] < 2 else 200)

    client = WordPressClient("https://brasileira.news", "u", "p")
    monkeypatch.setattr(client._client, "request", fake_request)
    response = await client.get("/wp-json/wp/v2/posts")
    await client.close()
    assert response["ok"] is True
    assert calls["count"] == 2
