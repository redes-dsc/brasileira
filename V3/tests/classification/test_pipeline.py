from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from classificador.classifier import MLClassifier
from classificador.ner_extractor import NERExtractor
from classificador.pipeline import ClassificationPipeline, RawArticle
from classificador.relevance_scorer import RelevanceScorer


@pytest_asyncio.fixture
async def full_pipeline() -> ClassificationPipeline:
    classifier = MLClassifier()
    await classifier.initialize()
    ner = NERExtractor()
    await ner.initialize()

    producer = AsyncMock()
    producer.send = AsyncMock()

    return ClassificationPipeline(
        ml_classifier=classifier,
        ner_extractor=ner,
        relevance_scorer=RelevanceScorer(),
        producer=producer,
        llm_fallback=None,
    )


@pytest.fixture
def sample_raw_article() -> RawArticle:
    now = datetime.now(timezone.utc)
    return RawArticle(
        article_id="test-uuid-1234",
        url="https://agenciabrasil.ebc.com.br/politica/teste",
        url_hash="sha256:abc123",
        fonte_id=42,
        fonte_nome="Agência Brasil",
        fonte_tipo="governo",
        fonte_peso=5,
        fonte_url="https://agenciabrasil.ebc.com.br",
        fonte_categoria_hint="politica",
        titulo="Senado aprova reforma tributária em votação histórica",
        conteudo_bruto="O Senado Federal aprovou nesta terça-feira a reforma tributária.",
        conteudo_html="<p>O Senado Federal aprovou...</p>",
        resumo="Aprovação histórica no Senado.",
        imagem_url="https://agenciabrasil.ebc.com.br/foto.jpg",
        tipo="rss",
        data_publicacao=now,
        data_coleta=now,
    )


@pytest.mark.asyncio
class TestClassificationPipeline:
    async def test_pipeline_completo(self, full_pipeline: ClassificationPipeline, sample_raw_article: RawArticle):
        result = await full_pipeline.classify(sample_raw_article)
        assert result.article_id == sample_raw_article.article_id
        assert result.categoria == "politica"
        assert result.categoria_wp_id == 2
        assert result.categoria_confidence > 0.5
        assert 0 <= result.score_relevancia <= 100
        assert result.urgencia in ("flash", "normal", "analise")
        assert len(result.tags_sugeridas) <= 5
        assert result.classificador_version == "3.0.0"

    async def test_entidades_extraidas(self, full_pipeline: ClassificationPipeline, sample_raw_article: RawArticle):
        result = await full_pipeline.classify(sample_raw_article)
        entities = result.entidades_pessoas + result.entidades_orgs + result.entidades_locais
        assert len(entities) > 0

    async def test_score_relevancia_fonte_governo(self, full_pipeline: ClassificationPipeline, sample_raw_article: RawArticle):
        result = await full_pipeline.classify(sample_raw_article)
        assert result.score_relevancia >= 60
