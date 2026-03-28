"""Classificador ML com sentence-transformers para 16 macrocategorias."""

from __future__ import annotations

import asyncio
import logging
import pickle
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
CACHE_PATH = Path("/tmp/category_centroids.pkl")

CATEGORY_PROTOTYPES: dict[str, list[str]] = {
    "politica": [
        "governo federal anuncia novas medidas", "deputados aprovam projeto de lei",
        "presidente assina decreto regulamentando", "eleições municipais disputa acirrada",
        "senado vota reforma política", "congresso debate orçamento público",
        "partidos políticos formam aliança", "ministro toma posse no cargo",
        "câmara dos deputados sessão plenária", "STF julga ação de inconstitucionalidade",
    ],
    "economia": [
        "bolsa de valores fecha em alta", "inflação acumula alta no semestre",
        "banco central define taxa selic", "PIB cresce no trimestre",
        "dólar sobe frente ao real", "mercado financeiro reage a dados",
        "investimentos estrangeiros aumentam", "desemprego cai segundo pesquisa",
        "balança comercial registra superávit", "reforma tributária impacta empresas",
    ],
    "esportes": [
        "campeonato brasileiro rodada decisiva", "seleção brasileira convocação jogadores",
        "time vence partida por gols", "olimpíadas medalha de ouro",
        "copa do mundo fase de grupos", "jogador transferência milionária",
        "técnico demitido após resultados ruins", "campeonato estadual final emocionante",
        "tênis grand slam semifinal", "fórmula 1 grande prêmio corrida",
    ],
    "tecnologia": [
        "inteligência artificial avanço significativo", "startup levanta rodada investimento",
        "aplicativo lança nova funcionalidade", "cibersegurança ataque hacker dados vazados",
        "rede social mudança algoritmo", "criptomoeda bitcoin valorização mercado",
        "smartphone lançamento inovação", "computação quântica pesquisa avanço",
        "internet 5G expansão cobertura", "big data análise empresarial",
    ],
    "saude": [
        "vacina aprovada pela anvisa", "sus amplia atendimento hospitalar",
        "pandemia novos casos crescem", "pesquisa médica descobre tratamento",
        "plano de saúde reajuste anual", "surto de dengue epidemia",
        "saúde mental ansiedade depressão tratamento", "hospital inaugurado nova unidade",
        "medicamento genérico disponível farmácias", "campanha vacinação crianças idosos",
    ],
    "educacao": [
        "enem resultado divulgação notas", "universidade vestibular aprovação",
        "escola pública ensino fundamental", "professor greve salário reajuste",
        "educação a distância crescimento", "bolsa de estudos programa federal",
        "analfabetismo taxa redução", "currículo escolar reforma base nacional",
        "creche vaga fila espera", "ensino técnico profissionalizante mercado trabalho",
    ],
    "ciencia": [
        "pesquisa científica publicação revista", "nasa missão espacial lançamento",
        "descoberta fóssil arqueológica", "mudança climática estudo impacto",
        "genoma sequenciamento dna", "energia renovável solar eólica",
        "telescópio observação galáxia", "robótica automação industrial",
        "biodiversidade espécie descoberta", "física quântica experimento",
    ],
    "cultura": [
        "festival de música shows internacionais", "filme estreia bilheteria cinema",
        "exposição arte museu galeria", "livro lançamento autor best-seller",
        "teatro peça espetáculo temporada", "carnaval desfile escola samba",
        "série streaming plataforma lançamento", "prêmio grammy oscar indicação",
        "patrimônio cultural tombamento restauração", "show musical turnê apresentação",
    ],
    "mundo": [
        "conflito geopolítico tensão internacional", "reunião cúpula líderes mundiais",
        "acordo comercial entre países", "guerra conflito armado vítimas",
        "eleição presidencial país estrangeiro", "tratado internacional assinatura",
        "refugiados migração crise humanitária", "diplomacia relações bilaterais",
        "organização nações unidas resolução", "economia global recessão crescimento",
    ],
    "meio_ambiente": [
        "desmatamento amazônia floresta queimadas", "aquecimento global temperatura recorde",
        "poluição ar qualidade cidade", "reciclagem resíduos sólidos coleta",
        "energia limpa sustentabilidade transição", "seca crise hídrica reservatórios",
        "biodiversidade extinção espécie ameaçada", "rio contaminação despejo esgoto",
        "parque ambiental preservação área protegida", "carbono emissão acordo climático",
    ],
    "seguranca": [
        "polícia operação prisão traficantes", "crime organizado facção investigação",
        "homicídio violência urbana estatística", "justiça julgamento condenação réu",
        "presídio sistema penitenciário superlotação", "assalto roubo furto ocorrência",
        "lei penal código reforma legislação", "ministério público denúncia promotor",
        "delegacia registro boletim ocorrência", "feminicídio violência doméstica proteção",
    ],
    "sociedade": [
        "desigualdade social pobreza renda", "direitos humanos igualdade inclusão",
        "movimento social protesto manifestação", "comunidade quilombola indígena reconhecimento",
        "habitação moradia programa social", "transporte público mobilidade urbana",
        "terceiro setor ong assistência social", "religião igreja culto comunidade",
        "família adoção custódia direitos", "urbanização cidade crescimento populacional",
    ],
    "brasil": [
        "brasil território nacional estados", "federação governo estados municípios",
        "brasileiro população censo demográfico", "nação país pátria identidade",
        "infraestrutura obras desenvolvimento nacional", "regiões norte sul sudeste nordeste",
        "cultura brasileira tradição identidade", "economia brasileira produção industrial",
        "política nacional debate público", "sociedade brasileira costume tradição",
    ],
    "regionais": [
        "estado governo estadual decreto", "cidade prefeitura administração municipal",
        "região metropolitana desenvolvimento local", "interior rural agricultura",
        "capital estado inauguração obra", "comunidade local bairro vizinhança",
        "prefeito eleição câmara vereadores", "escola municipal estadual matrícula",
        "hospital regional atendimento saúde", "estrada rodovia duplicação manutenção",
    ],
    "opiniao": [
        "análise editorial opinião colunista", "artigo debate perspectiva ponto de vista",
        "coluna comentário reflexão crítica", "entrevista especialista avaliação cenário",
        "editorial posicionamento jornal", "crônica texto autoral observação",
        "carta leitor público opinião", "debate acadêmico pesquisador especialista",
        "perspectiva futuro tendência previsão", "crítica review avaliação produto serviço",
    ],
    "ultimas_noticias": [
        "urgente última hora breaking news", "agora pouco acaba de acontecer",
        "atualização momento notícia urgente", "alerta flash informação imediata",
        "cobertura ao vivo tempo real", "plantão notícias atualização minuto",
    ],
}

# IDs de categorias WordPress
CATEGORY_TO_WP_ID: dict[str, int] = {
    "politica": 3, "economia": 4, "esportes": 5, "tecnologia": 6,
    "saude": 7, "educacao": 8, "ciencia": 9, "cultura": 10,
    "mundo": 11, "meio_ambiente": 12, "seguranca": 13, "sociedade": 15,
    "brasil": 14, "regionais": 16, "opiniao": 18, "ultimas_noticias": 1,
}


class MLClassifier:
    """Classificador baseado em sentence-transformers com cosine similarity."""

    def __init__(self):
        self._model = None
        self._centroids: dict[str, np.ndarray] = {}
        self._ready = False

    async def initialize(self) -> None:
        """Carrega modelo e computa centroids (ou lê do cache)."""
        if self._ready:
            return

        # Tenta cache primeiro
        if CACHE_PATH.exists():
            try:
                with open(CACHE_PATH, "rb") as f:
                    self._centroids = pickle.load(f)
                self._ready = True
                logger.info("Centroids carregados do cache (%d categorias)", len(self._centroids))
                return
            except Exception:
                logger.warning("Cache de centroids corrompido, recomputando")

        # Carrega modelo em thread separada (blocking)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._load_model_and_centroids)
        self._ready = True

    def _load_model_and_centroids(self) -> None:
        """Carrega sentence-transformers e computa centroids (blocking)."""
        from sentence_transformers import SentenceTransformer

        logger.info("Carregando modelo %s...", MODEL_NAME)
        self._model = SentenceTransformer(MODEL_NAME)

        for category, phrases in CATEGORY_PROTOTYPES.items():
            embeddings = self._model.encode(phrases, normalize_embeddings=True)
            self._centroids[category] = np.mean(embeddings, axis=0)

        # Salva cache
        try:
            with open(CACHE_PATH, "wb") as f:
                pickle.dump(self._centroids, f)
            logger.info("Centroids salvos em cache")
        except Exception:
            logger.warning("Falha ao salvar cache de centroids")

    async def classify(self, text: str) -> tuple[str, float]:
        """Classifica texto retornando (categoria, confiança)."""
        if not self._ready:
            await self.initialize()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._classify_sync, text)

    def _classify_sync(self, text: str) -> tuple[str, float]:
        """Classificação síncrona (roda em executor)."""
        if self._model is None:
            # Fallback: carregar modelo se só temos centroids do cache
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(MODEL_NAME)

        text_embedding = self._model.encode([text[:512]], normalize_embeddings=True)[0]

        scores: dict[str, float] = {}
        for category, centroid in self._centroids.items():
            similarity = float(np.dot(text_embedding, centroid))
            scores[category] = similarity

        best_cat = max(scores, key=scores.get)
        best_score = scores[best_cat]

        # Segundo melhor para calcular margem de confiança
        sorted_scores = sorted(scores.values(), reverse=True)
        margin = sorted_scores[0] - sorted_scores[1] if len(sorted_scores) > 1 else 0
        confidence = min(0.98, max(0.1, best_score * 0.7 + margin * 1.5))

        return best_cat, confidence

    def get_wp_category_id(self, category: str) -> int:
        """Retorna WP category ID para a categoria."""
        return CATEGORY_TO_WP_ID.get(category, 1)
