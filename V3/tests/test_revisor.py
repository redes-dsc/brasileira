from __future__ import annotations

import pytest

from revisor.revisor import RevisorAgent


class FakeWP:
    def __init__(self):
        self.patches = []

    async def get(self, endpoint: str):
        return {
            "id": 10,
            "title": {"rendered": "titulo de teste!!"},
            "content": {"rendered": "Texto  afim de validar."},
            "excerpt": {"rendered": "  resumo curto  "},
        }

    async def patch(self, endpoint: str, json: dict):
        self.patches.append((endpoint, json))
        return {"id": 10}


class FakeRedis:
    def __init__(self):
        self.store = {}

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    async def delete(self, key):
        self.store.pop(key, None)

    async def hincrby(self, *args, **kwargs):
        return 1


class FakeDBAcquire:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    async def execute(self, *args, **kwargs):
        return None


class FakeDBPool:
    def acquire(self):
        return FakeDBAcquire()


@pytest.mark.asyncio
async def test_revisor_aplica_patch_sem_status() -> None:
    agent = RevisorAgent(wp_client=FakeWP(), redis_client=FakeRedis(), db_pool=FakeDBPool())
    result = await agent.processar_evento({"post_id": 10, "titulo": "x"})
    assert result.post_id == 10
    assert result.patch_aplicado is True
    endpoint, payload = agent.wp_client.patches[0]
    assert endpoint.endswith("/10")
    assert "status" not in payload
    assert "slug" not in payload
