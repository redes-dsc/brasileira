import pytest
import pytest_asyncio

from classificador.ner_extractor import NERExtractor, filter_entities


@pytest_asyncio.fixture
async def ner() -> NERExtractor:
    extractor = NERExtractor()
    await extractor.initialize()
    return extractor


@pytest.mark.asyncio
class TestNERExtractor:
    async def test_extrai_pessoas(self, ner: NERExtractor):
        entities = await ner.extract(
            titulo="Lula assina decreto em cerimônia no Planalto",
            conteudo="O presidente Luiz Inácio Lula da Silva assinou hoje.",
        )
        assert len(entities.pessoas) > 0

    async def test_extrai_organizacoes(self, ner: NERExtractor):
        entities = await ner.extract(
            titulo="Petrobras anuncia novo campo",
            conteudo="A Petrobras divulgou descoberta em parceria com o INPE.",
        )
        assert any("Petrobras" in org for org in entities.organizacoes)

    async def test_extrai_locais(self, ner: NERExtractor):
        entities = await ner.extract(
            titulo="Enchente em Porto Alegre deixa famílias desalojadas",
            conteudo="A cidade de Porto Alegre no Brasil registrou novos pontos.",
        )
        assert any("Porto Alegre" in place for place in entities.locais)

    async def test_entidade_principal(self, ner: NERExtractor):
        entities = await ner.extract(
            titulo="Bolsonaro depôs na Polícia Federal",
            conteudo="O ex-presidente Jair Bolsonaro prestou depoimento.",
        )
        assert entities.entidade_principal is not None

    async def test_filtro_stoplist(self, ner: NERExtractor):
        entities = await ner.extract(
            titulo="Governo Federal anuncia novo programa",
            conteudo="O Governo Federal lançou programa para empresas.",
        )
        filtered = filter_entities(entities)
        assert "Governo" not in filtered.organizacoes

    async def test_tags_wordpress_max5(self, ner: NERExtractor):
        entities = await ner.extract(
            titulo="Reunião envolveu Lula, Pacheco, Lira, Haddad, Dino, Gonet, Alexandre",
            conteudo="A reunião no Palácio do Planalto reuniu diversas autoridades.",
        )
        assert len(entities.tags_wordpress) <= 5
