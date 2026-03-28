"""Classificador ML com sentence-transformers (embeddings zero-shot) para 16 macrocategorias."""

from __future__ import annotations

import asyncio
import logging
import pickle
from pathlib import Path
import numpy as np

logger = logging.getLogger(__name__)

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
CACHE_PATH = Path("/tmp/category_centroids_v3_st.pkl")

# Slugs alinhados a WordPress; frases em PT para embeddings (paraphrase-multilingual).
CATEGORY_PROTOTYPES: dict[str, list[str]] = {
    "politica": [
        "governo federal anuncia medida",
        "presidente assina decreto",
        "congresso nacional vota projeto de lei",
        "senado e câmara dos deputados",
        "eleições e partidos políticos",
    ],
    "economia": [
        "banco central define taxa de juros selic",
        "inflação e índice de preços ao consumidor",
        "mercado financeiro bolsa de valores",
        "PIB e crescimento econômico do Brasil",
        "dólar câmbio e comércio exterior",
    ],
    "esportes": [
        "campeonato brasileiro série A futebol",
        "seleção brasileira convocação jogos",
        "Corinthians Flamengo Palmeiras São Paulo",
        "olimpíadas e competição esportiva",
        "transferência de jogador contratação",
    ],
    "tecnologia": [
        "inteligência artificial e machine learning",
        "startup e inovação tecnológica",
        "smartphone celular e aplicativo",
        "cibersegurança e proteção de dados",
        "redes sociais e plataformas digitais",
    ],
    "saude": [
        "ministério da saúde vacinação SUS",
        "epidemia pandemia e doença infecciosa",
        "hospital e atendimento médico",
        "medicamento e tratamento de saúde",
        "saúde mental e bem-estar",
    ],
    "educacao": [
        "escola universidade e ensino",
        "ENEM vestibular e educação superior",
        "MEC e política educacional",
        "professor e sala de aula",
        "pesquisa acadêmica e ciência",
    ],
    "ciencia": [
        "descoberta científica e pesquisa",
        "NASA espaço e astronomia",
        "mudança climática e meio ambiente",
        "estudo publicado em revista científica",
        "tecnologia e inovação científica",
    ],
    "cultura": [
        "festival de música e show ao vivo",
        "cinema filme e série de TV",
        "livro literatura e autor",
        "exposição de arte e museu",
        "cultura popular e entretenimento",
    ],
    "mundo": [
        "guerra conflito e tensão geopolítica",
        "ONU e diplomacia internacional",
        "Estados Unidos China e Rússia",
        "União Europeia e comércio global",
        "imigrantes refugiados e fronteiras",
    ],
    "meio_ambiente": [
        "desmatamento e Amazônia",
        "mudança climática e aquecimento global",
        "poluição e contaminação ambiental",
        "energia renovável e sustentabilidade",
        "fauna flora e biodiversidade",
    ],
    "seguranca": [
        "polícia operação e crime organizado",
        "violência e segurança pública",
        "tráfico de drogas e prisão",
        "homicídio e investigação policial",
        "sistema penitenciário e justiça criminal",
    ],
    "sociedade": [
        "desigualdade social e pobreza",
        "direitos humanos e inclusão social",
        "moradia e habitação popular",
        "transporte público e mobilidade urbana",
        "comunidade e ação social",
    ],
    "brasil": [
        "notícia geral do Brasil",
        "estados e municípios brasileiros",
        "cultura brasileira e identidade nacional",
        "infraestrutura e desenvolvimento regional",
        "serviço público e cidadania",
    ],
    "regionais": [
        "notícia local e regional",
        "prefeitura e governo estadual",
        "cidade e comunidade local",
        "desenvolvimento regional",
        "evento e acontecimento local",
    ],
    "opiniao": [
        "coluna de opinião e editorial",
        "análise política e comentário",
        "crítica e ponto de vista",
        "debate e argumentação",
        "crônica e ensaio",
    ],
    "ultimas_noticias": [
        "urgente e breaking news",
        "última hora e plantão",
        "acidente e tragédia",
        "evento inesperado e emergência",
        "alerta e aviso importante",
    ],
}

# IDs de categorias WordPress
CATEGORY_TO_WP_ID: dict[str, int] = {
    "politica": 3,
    "economia": 4,
    "esportes": 5,
    "tecnologia": 6,
    "saude": 7,
    "educacao": 8,
    "ciencia": 9,
    "cultura": 10,
    "mundo": 11,
    "meio_ambiente": 12,
    "seguranca": 13,
    "sociedade": 15,
    "brasil": 14,
    "regionais": 16,
    "opiniao": 18,
    "ultimas_noticias": 1,
}


class MLClassifier:
    """Classificador por similaridade de cosseno entre embedding do texto e centróides por categoria."""

    def __init__(self) -> None:
        self._model = None
        self._centroids: dict[str, np.ndarray] = {}
        self._ready = False

    async def initialize(self) -> None:
        """Carrega modelo e computa centróides (ou lê do cache)."""
        if self._ready:
            return

        if CACHE_PATH.exists():
            try:
                with open(CACHE_PATH, "rb") as f:
                    self._centroids = pickle.load(f)
                self._ready = True
                logger.info("Centroids carregados do cache (%d categorias)", len(self._centroids))
                return
            except Exception:
                logger.warning("Cache de centroids corrompido, recomputando")

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._load_model_and_centroids)
        self._ready = True

    def _load_model_and_centroids(self) -> None:
        from sentence_transformers import SentenceTransformer

        logger.info("Carregando modelo %s...", MODEL_NAME)
        self._model = SentenceTransformer(MODEL_NAME)

        for category, phrases in CATEGORY_PROTOTYPES.items():
            embeddings = self._model.encode(phrases)
            self._centroids[category] = np.mean(embeddings, axis=0)

        try:
            with open(CACHE_PATH, "wb") as f:
                pickle.dump(self._centroids, f)
            logger.info("Centroids salvos em cache")
        except Exception:
            logger.warning("Falha ao salvar cache de centroids")

    async def classify(
        self,
        title: str = "",
        body: str = "",
        *,
        titulo: str | None = None,
        conteudo: str | None = None,
        fonte_categoria_hint: str | None = None,
    ) -> tuple[str, float]:
        """Classifica texto retornando (categoria_slug, confiança como similaridade de cosseno)."""
        if not self._ready:
            await self.initialize()

        t = titulo if titulo is not None else title
        b = conteudo if conteudo is not None else body
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._classify_sync,
            t,
            b,
            fonte_categoria_hint,
        )

    def _classify_sync(
        self,
        title: str,
        body: str = "",
        fonte_categoria_hint: str | None = None,
    ) -> tuple[str, float]:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(MODEL_NAME)

        text = f"{title}. {body[:500]}" if body else title
        embedding = self._model.encode(text)

        best_cat = "brasil"
        best_score = 0.0

        for cat, centroid in self._centroids.items():
            denom = np.linalg.norm(embedding) * np.linalg.norm(centroid)
            if denom == 0:
                continue
            similarity = float(np.dot(embedding, centroid) / denom)
            if similarity > best_score:
                best_score = similarity
                best_cat = cat

        if fonte_categoria_hint:
            hint = fonte_categoria_hint.strip().lower().replace(" ", "_").replace("-", "_")
            if hint == best_cat:
                best_score = min(1.0, best_score + 0.05)

        return best_cat, best_score

    @property
    def category_centroids(self) -> dict[str, np.ndarray]:
        """Centróides por categoria (útil para testes/diagnóstico)."""
        return self._centroids

    def get_wp_category_id(self, category: str) -> int:
        """Retorna WP category ID para a categoria."""
        return CATEGORY_TO_WP_ID.get(category, 1)
