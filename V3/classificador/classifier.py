"""Classificador semântico leve para 16 macrocategorias."""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "politica": ("senado", "câmara", "governo", "presidente", "congresso", "deputado"),
    "economia": ("economia", "inflação", "selic", "mercado", "ibovespa", "dólar"),
    "esportes": ("futebol", "campeonato", "jogo", "atleta", "time", "olimp"),
    "tecnologia": ("tecnologia", "ia", "inteligencia artificial", "startup", "software", "app"),
    "saude": ("saúde", "hospital", "vacina", "médico", "sus", "diagnóstico"),
    "educacao": ("educação", "escola", "universidade", "enem", "aluno", "professor"),
    "ciencia": ("cient", "pesquisa", "estudo", "laboratório", "inpe", "nasa"),
    "cultura_entretenimento": ("filme", "música", "show", "série", "teatro", "festival"),
    "mundo_internacional": ("internacional", "onu", "guerra", "europa", "eua", "china"),
    "meio_ambiente": ("amazônia", "desmatamento", "clima", "meio ambiente", "sustentabilidade"),
    "seguranca_justica": ("polícia", "justiça", "tribunal", "prisão", "crime", "stf"),
    "sociedade": ("sociedade", "comunidade", "direitos", "cidadania", "inclusão"),
    "brasil": ("brasil", "brasileiro", "nacional", "federal"),
    "regionais": ("cidade", "estado", "prefeitura", "regional", "interior"),
    "opiniao_analise": ("opinião", "analise", "coluna", "editorial", "cenário"),
    "ultimas_noticias": ("urgente", "agora", "última hora", "breaking"),
}


@dataclass(slots=True)
class ClassificationResult:
    categoria: str
    confianca: float


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\s+", " ", text)
    return text


class MLClassifier:
    """Classificador por similaridade lexical (rápido, local e determinístico)."""

    def __init__(self) -> None:
        self.category_centroids: dict[str, tuple[str, ...]] = CATEGORY_KEYWORDS

    async def initialize(self) -> None:
        """Hook assíncrono para compatibilidade com pipeline."""

    async def classify(
        self,
        titulo: str,
        conteudo: str,
        fonte_categoria_hint: str | None = None,
    ) -> ClassificationResult:
        """Classifica artigo e retorna categoria + confiança."""

        text = _normalize(f"{titulo} {conteudo}")
        scores: dict[str, float] = {}

        for category, keywords in self.category_centroids.items():
            score = 0.0
            for keyword in keywords:
                keyword_norm = _normalize(keyword)
                if keyword_norm in text:
                    score += 1.0
            scores[category] = score

        best = max(scores, key=scores.get)
        sorted_scores = sorted(scores.values(), reverse=True)
        best_score = sorted_scores[0]
        second = sorted_scores[1] if len(sorted_scores) > 1 else 0.0

        confidence = 0.5
        if best_score > 0:
            confidence = min(0.98, 0.55 + (best_score - second) * 0.08 + best_score * 0.03)

        if fonte_categoria_hint:
            hint = fonte_categoria_hint.strip().lower()
            if hint == best:
                confidence = min(0.99, confidence + 0.05)

        return ClassificationResult(categoria=best, confianca=round(confidence, 4))
