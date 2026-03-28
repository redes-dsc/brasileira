from __future__ import annotations

import pytest

from curador_homepage.acf_applicator import ACFAplicator
from curador_homepage.layout_manager import LayoutManager


def test_layout_breaking_tem_prioridade() -> None:
    manager = LayoutManager()
    ranked = [{"post_id": 1, "score_final": 92}]
    decision = manager.decidir(ranked, breaking_candidate={"post_id": 999})
    assert decision.layout == "breaking"
    assert decision.breaking_post_id == 999


def test_layout_amplo_por_score() -> None:
    manager = LayoutManager()
    ranked = [{"post_id": 1, "score_final": 85}]
    decision = manager.decidir(ranked)
    assert decision.layout == "amplo"


class DummyWPClient:
    def __init__(self) -> None:
        self.get_calls: list[str] = []
        self.post_calls: list[tuple[str, dict]] = []
        self.fields = {}

    async def get(self, endpoint: str):
        self.get_calls.append(endpoint)
        if endpoint == "/wp-json/acf/v3/options/homepage-settings":
            return {"acf": self.fields}
        raise RuntimeError(f"Falha na chamada WordPress GET {endpoint}: 404 Not Found")

    async def post(self, endpoint: str, json: dict):
        self.post_calls.append((endpoint, json))
        return {"ok": True}


class DummyWPClientNoACF:
    async def get(self, endpoint: str):
        raise RuntimeError(f"Falha na chamada WordPress GET {endpoint}: 404 Not Found")

    async def post(self, endpoint: str, json: dict):
        return {"ok": True}


@pytest.mark.asyncio
async def test_acf_applicator_resolve_endpoint_com_fallback() -> None:
    app = ACFAplicator()
    wp = DummyWPClient()
    payload = {
        "layout": "normal",
        "manchete_principal": 100,
        "breaking_post_id": None,
        "destaques": [{"post_id": 100, "tamanho": "normal", "label": "Destaque"}],
        "mais_lidas_posts": [100, 200],
        "timestamp": "2026-03-26T00:00:00Z",
        "ciclo_id": "abc",
        "editorias": {"ultimas_noticias": [100, 200]},
    }

    result = await app.aplicar_atomico(wp, payload)
    assert result["updated"] is True
    assert wp.post_calls[0][0] == "/wp-json/acf/v3/options/homepage-settings"
    assert "/wp-json/acf/v3/options/homepage-settings" in wp.get_calls


@pytest.mark.asyncio
async def test_acf_applicator_skip_quando_acf_indisponivel() -> None:
    app = ACFAplicator()
    wp = DummyWPClientNoACF()
    payload = {
        "layout": "normal",
        "manchete_principal": 100,
        "breaking_post_id": None,
        "destaques": [{"post_id": 100, "tamanho": "normal", "label": "Destaque"}],
        "mais_lidas_posts": [100, 200],
        "timestamp": "2026-03-26T00:00:00Z",
        "ciclo_id": "abc",
        "editorias": {"ultimas_noticias": [100, 200]},
    }
    result = await app.aplicar_atomico(wp, payload)
    assert result["updated"] is False
    assert result["skipped"] is True
    assert result["reason"] == "acf_unavailable"
