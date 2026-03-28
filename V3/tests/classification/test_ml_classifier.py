import pytest
import pytest_asyncio

from classificador.classifier import MLClassifier


@pytest_asyncio.fixture
async def classifier() -> MLClassifier:
    model = MLClassifier()
    await model.initialize()
    return model


@pytest.mark.asyncio
class TestMLClassifier:
    async def test_politica(self, classifier: MLClassifier):
        categoria, _confianca = await classifier.classify(
            titulo="Senado aprova reforma tributária",
            conteudo="A Câmara e o Congresso discutem projeto do governo federal.",
        )
        assert categoria == "politica"

    async def test_tecnologia_ia(self, classifier: MLClassifier):
        categoria, _confianca = await classifier.classify(
            titulo="Startup usa inteligência artificial para diagnóstico",
            conteudo="Aplicativo com IA reduz tempo de análise médica.",
        )
        assert categoria == "tecnologia"

    async def test_meio_ambiente(self, classifier: MLClassifier):
        categoria, _confianca = await classifier.classify(
            titulo="Desmatamento na Amazônia cresce, diz INPE",
            conteudo="Dados de clima e meio ambiente acendem alerta.",
        )
        assert categoria == "meio_ambiente"

    async def test_ambiguidade_baixa_confianca(self, classifier: MLClassifier):
        _categoria, confianca = await classifier.classify(
            titulo="Empresa anuncia mudanças no setor",
            conteudo="Mudanças foram anunciadas ontem.",
        )
        assert confianca < 0.75

    async def test_fonte_hint_consistente(self, classifier: MLClassifier):
        sem_hint = await classifier.classify(
            titulo="Câmara votou o projeto aprovado",
            conteudo="A Câmara dos Deputados aprovou projeto de lei.",
        )
        com_hint = await classifier.classify(
            titulo="Câmara votou o projeto aprovado",
            conteudo="A Câmara dos Deputados aprovou projeto de lei.",
            fonte_categoria_hint="politica",
        )
        assert com_hint[1] >= sem_hint[1] - 0.05

    async def test_todas_16_categorias_funcionam(self, classifier: MLClassifier):
        assert len(classifier.category_centroids) == 16
