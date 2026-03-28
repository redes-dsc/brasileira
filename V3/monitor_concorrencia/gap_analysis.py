"""Análise TF-IDF cosine para cobertura concorrente."""

from __future__ import annotations

from .config import MonitorConcorrenciaConfig
from .normalizacao import normalize_portuguese
from .schemas import CoverageResult, PortalArticle


class GapAnalyzer:
    """Classifica cobertura: coberto/parcial/gap via TF-IDF + cosseno."""

    def __init__(self, config: MonitorConcorrenciaConfig | None = None):
        self.config = config or MonitorConcorrenciaConfig()

    async def classify(self, concorrentes: list[PortalArticle], nossos_titulos: list[str]) -> list[CoverageResult]:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        our_docs_raw = [t for t in nossos_titulos if t.strip()]
        competitor_docs_raw = [item.titulo for item in concorrentes if item.titulo.strip()]
        if not our_docs_raw or not competitor_docs_raw:
            return []

        our_docs = [" ".join(normalize_portuguese(t)) for t in our_docs_raw]
        competitor_docs = [" ".join(normalize_portuguese(t)) for t in competitor_docs_raw]
        corpus = our_docs + competitor_docs
        if not any(corpus):
            return []

        vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
        tfidf_matrix = vectorizer.fit_transform(corpus)
        our_matrix = tfidf_matrix[: len(our_docs)]
        competitor_matrix = tfidf_matrix[len(our_docs) :]

        results: list[CoverageResult] = []
        for idx, article in enumerate(concorrentes):
            if idx >= competitor_matrix.shape[0]:
                break
            sims = cosine_similarity(competitor_matrix[idx], our_matrix)
            best = float(sims.max()) if sims.size else 0.0
            if best >= self.config.covered_threshold:
                status = "coberto"
                topic = ""
            elif best >= self.config.partial_threshold:
                status = "parcial"
                topic = "consolidacao"
            else:
                status = "gap"
                topic = "pautas-gap"
            norm_tokens = normalize_portuguese(article.titulo)
            norm = "_".join(norm_tokens[:6]) or "topico_sem_nome"
            results.append(
                CoverageResult(
                    titulo=article.titulo,
                    status=status,
                    similaridade=best,
                    topico_destino=topic,
                    topico_normalizado=norm,
                )
            )
        return results
