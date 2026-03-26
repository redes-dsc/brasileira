from datetime import datetime, timedelta, timezone

from classificador.relevance_scorer import RelevanceScorer, Urgencia


class TestRelevanceScorer:
    def setup_method(self):
        self.scorer = RelevanceScorer()

    def test_score_range_valido(self):
        result = self.scorer.score("Título de teste", "Conteúdo de teste")
        assert 0 <= result.score <= 100

    def test_fonte_governo_tem_score_maior(self):
        gov = self.scorer.score(
            "Ministério anuncia programa",
            "Portaria oficial publicada.",
            fonte_tier="governo",
            fonte_peso=5,
        )
        nicho = self.scorer.score(
            "Ministério anuncia programa",
            "Portaria oficial publicada.",
            fonte_tier="nicho",
            fonte_peso=3,
        )
        assert gov.score > nicho.score

    def test_urgencia_breaking_news(self):
        result = self.scorer.score(
            "URGENTE: Explosão em Brasília deixa feridos",
            "Explosão ocorreu há pouco na capital federal.",
        )
        assert result.urgencia == Urgencia.FLASH

    def test_urgencia_analise(self):
        result = self.scorer.score(
            "Análise: O impacto da reforma tributária",
            "Esta análise examina perspectivas.",
            categoria="opiniao_analise",
        )
        assert result.urgencia == Urgencia.ANALISE

    def test_artigo_velho_perde_score(self):
        now = datetime.now(timezone.utc)
        recent = self.scorer.score("Mesmo título", "Mesmo conteúdo", data_publicacao=now - timedelta(minutes=30))
        old = self.scorer.score("Mesmo título", "Mesmo conteúdo", data_publicacao=now - timedelta(hours=12))
        assert recent.score > old.score

    def test_breakdown_tem_todos_fatores(self):
        result = self.scorer.score("Presidente assina decreto econômico", "Texto completo")
        keys = {"baseline", "tier_fonte", "peso_fonte", "keywords", "frescor", "titulo_qualidade", "score_final"}
        assert keys.issubset(set(result.breakdown.keys()))
