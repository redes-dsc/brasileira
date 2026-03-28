"""Testes do ClassificationPipeline com mocks (API dict + classifier/NER/scorer/router)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from classificador.ner_extractor import NERResult
from classificador.pipeline import CATEGORY_TO_WP_ID, ClassificationPipeline, LLM_FALLBACK_THRESHOLD


def _sample_payload() -> dict:
    return {
        "article_id": "test-uuid-1234",
        "titulo": "Senado aprova reforma tributária em votação histórica",
        "resumo": "Aprovação histórica no Senado Federal.",
        "fonte_tier": "governo",
        "data_publicacao": "2025-01-15T12:00:00+00:00",
    }


def _ner_sample() -> NERResult:
    return NERResult(
        pessoas=["Fulano"],
        organizacoes=["Senado Federal"],
        locais=["Brasília"],
        misc=[],
        entidade_principal="Fulano",
        tags_wordpress=["Fulano", "Senado Federal", "Brasília"],
    )


@pytest.fixture
def mock_classifier() -> AsyncMock:
    m = AsyncMock()
    m.classify = AsyncMock(return_value=("politica", 0.85))
    return m


@pytest.fixture
def mock_ner() -> AsyncMock:
    m = AsyncMock()
    m.extract = AsyncMock(return_value=_ner_sample())
    return m


@pytest.fixture
def mock_scorer() -> MagicMock:
    m = MagicMock()
    m.score = MagicMock(
        return_value={
            "score": 72.5,
            "urgencia": "normal",
            "breakdown": {},
        }
    )
    return m


@pytest.fixture
def mock_router() -> AsyncMock:
    r = AsyncMock()
    r.route_request = AsyncMock(
        return_value=SimpleNamespace(content="tecnologia")
    )
    return r


@pytest.fixture
def pipeline_mocks(
    mock_classifier: AsyncMock,
    mock_ner: AsyncMock,
    mock_scorer: MagicMock,
) -> ClassificationPipeline:
    return ClassificationPipeline(
        classifier=mock_classifier,
        ner_extractor=mock_ner,
        scorer=mock_scorer,
        router=None,
    )


@pytest.fixture
def pipeline_with_router(
    mock_classifier: AsyncMock,
    mock_ner: AsyncMock,
    mock_scorer: MagicMock,
    mock_router: AsyncMock,
) -> ClassificationPipeline:
    return ClassificationPipeline(
        classifier=mock_classifier,
        ner_extractor=mock_ner,
        scorer=mock_scorer,
        router=mock_router,
    )


@pytest.mark.asyncio
class TestClassificationPipeline:
    async def test_classify_payload_returns_expected_fields(
        self,
        pipeline_mocks: ClassificationPipeline,
        mock_classifier: AsyncMock,
        mock_ner: AsyncMock,
        mock_scorer: MagicMock,
    ):
        payload = _sample_payload()
        result = await pipeline_mocks.classify(payload)

        assert result is not None
        assert result["editoria"] == "politica"
        assert result["categoria_wp_id"] == CATEGORY_TO_WP_ID["politica"]
        assert result["relevancia_score"] == 72.5
        assert result["urgencia"] == "normal"
        assert result["confianca_classificacao"] == 0.85

        entidades = result["entidades"]
        assert entidades["pessoas"] == ["Fulano"]
        assert entidades["organizacoes"] == ["Senado Federal"]
        assert entidades["locais"] == ["Brasília"]

        mock_classifier.classify.assert_awaited_once_with(
            payload["titulo"],
            payload["resumo"],
        )
        mock_ner.extract.assert_awaited_once()
        called_text = mock_ner.extract.await_args[0][0]
        assert payload["titulo"] in called_text
        assert payload["resumo"] in called_text
        mock_scorer.score.assert_called_once()
        score_kw = mock_scorer.score.call_args[1]
        assert score_kw["entities"]["pessoas"] == entidades["pessoas"]

    async def test_classify_merges_payload_into_result(
        self,
        pipeline_mocks: ClassificationPipeline,
    ):
        payload = _sample_payload()
        result = await pipeline_mocks.classify(payload)
        assert result["article_id"] == payload["article_id"]
        assert result["titulo"] == payload["titulo"]

    async def test_fonte_tier_from_tier_alias(
        self,
        mock_classifier: AsyncMock,
        mock_ner: AsyncMock,
        mock_scorer: MagicMock,
    ):
        mock_classifier.classify = AsyncMock(return_value=("economia", 0.9))
        pl = ClassificationPipeline(mock_classifier, mock_ner, mock_scorer, router=None)
        payload = {"titulo": "x", "resumo": "y", "tier": "vip"}
        await pl.classify(payload)
        mock_scorer.score.assert_called_once()
        assert mock_scorer.score.call_args[1]["fonte_tier"] == "vip"

    async def test_llm_fallback_when_confidence_below_threshold(
        self,
        pipeline_with_router: ClassificationPipeline,
        mock_classifier: AsyncMock,
        mock_router: AsyncMock,
    ):
        mock_classifier.classify = AsyncMock(return_value=("brasil", 0.35))
        mock_router.route_request = AsyncMock(
            return_value=SimpleNamespace(content="  Politica  ")
        )
        payload = {"titulo": "Notícia ambígua", "resumo": "Corpo curto."}
        result = await pipeline_with_router.classify(payload)

        assert result["editoria"] == "politica"
        assert result["categoria_wp_id"] == CATEGORY_TO_WP_ID["politica"]
        assert result["confianca_classificacao"] == max(0.35, 0.7)
        mock_router.route_request.assert_awaited_once()

    async def test_llm_fallback_skipped_when_router_none(
        self,
        mock_classifier: AsyncMock,
        mock_ner: AsyncMock,
        mock_scorer: MagicMock,
    ):
        mock_classifier.classify = AsyncMock(return_value=("cultura", 0.2))
        pl = ClassificationPipeline(mock_classifier, mock_ner, mock_scorer, router=None)
        result = await pl.classify({"titulo": "t", "resumo": "r"})
        assert result["editoria"] == "cultura"
        assert result["confianca_classificacao"] == 0.2

    async def test_llm_fallback_graceful_on_router_failure(
        self,
        pipeline_with_router: ClassificationPipeline,
        mock_classifier: AsyncMock,
        mock_router: AsyncMock,
    ):
        """Com confiança baixa, falha do LLM não derruba o pipeline."""
        mock_classifier.classify = AsyncMock(return_value=("saude", 0.4))
        mock_router.route_request = AsyncMock(side_effect=RuntimeError("LLM indisponível"))
        result = await pipeline_with_router.classify({"titulo": "Saúde pública", "resumo": "SUS."})

        assert result["editoria"] == "saude"
        assert result["confianca_classificacao"] == 0.4
        assert result["categoria_wp_id"] == CATEGORY_TO_WP_ID["saude"]

    async def test_llm_returns_unknown_category_keeps_ml_editoria(
        self,
        pipeline_with_router: ClassificationPipeline,
        mock_classifier: AsyncMock,
        mock_router: AsyncMock,
    ):
        mock_classifier.classify = AsyncMock(return_value=("esportes", 0.5))
        mock_router.route_request = AsyncMock(
            return_value=SimpleNamespace(content="categoria_inventada_xyz")
        )
        result = await pipeline_with_router.classify({"titulo": "Jogo", "resumo": "Placar."})
        assert result["editoria"] == "esportes"
        assert result["confianca_classificacao"] == 0.5

    async def test_graceful_failure_scorer_raises_propagates(
        self,
        mock_classifier: AsyncMock,
        mock_ner: AsyncMock,
        mock_scorer: MagicMock,
    ):
        mock_scorer.score = MagicMock(side_effect=ValueError("scorer quebrado"))
        pl = ClassificationPipeline(mock_classifier, mock_ner, mock_scorer, router=None)
        with pytest.raises(ValueError, match="scorer quebrado"):
            await pl.classify({"titulo": "t", "resumo": "r"})

    async def test_graceful_failure_classifier_raises_propagates(
        self,
        mock_classifier: AsyncMock,
        mock_ner: AsyncMock,
        mock_scorer: MagicMock,
    ):
        mock_classifier.classify = AsyncMock(side_effect=RuntimeError("modelo offline"))
        pl = ClassificationPipeline(mock_classifier, mock_ner, mock_scorer, router=None)
        with pytest.raises(RuntimeError, match="modelo offline"):
            await pl.classify({"titulo": "t", "resumo": "r"})


def test_llm_fallback_threshold_constant():
    assert LLM_FALLBACK_THRESHOLD == 0.6
