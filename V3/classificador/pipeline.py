"""Pipeline de classificação: ML -> (LLM fallback) -> NER -> scoring."""

from __future__ import annotations

import logging
from typing import Any, Optional

from shared.schemas import LLMRequest

logger = logging.getLogger(__name__)

CATEGORY_TO_WP_ID: dict[str, int] = {
    "politica": 3, "economia": 4, "esportes": 5, "tecnologia": 6,
    "saude": 7, "educacao": 8, "ciencia": 9, "cultura": 10,
    "mundo": 11, "meio_ambiente": 12, "seguranca": 13, "sociedade": 15,
    "brasil": 14, "regionais": 16, "opiniao": 18, "ultimas_noticias": 1,
}

LLM_FALLBACK_THRESHOLD = 0.6


class ClassificationPipeline:
    """Orquestra classifier + NER + scorer com LLM fallback."""

    def __init__(self, classifier, ner_extractor, scorer, router=None):
        self.classifier = classifier
        self.ner = ner_extractor
        self.scorer = scorer
        self.router = router

    async def classify(self, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Pipeline completo de classificação."""
        try:
            titulo = payload.get("titulo", "")
            resumo = payload.get("resumo", "")
            text = f"{titulo}. {resumo}"

            # ML classification
            editoria, confidence = await self.classifier.classify(text)

            # LLM fallback se confiança baixa
            if confidence < LLM_FALLBACK_THRESHOLD and self.router is not None:
                llm_editoria = await self._llm_classify(titulo, resumo)
                if llm_editoria:
                    editoria = llm_editoria
                    confidence = max(confidence, 0.7)

            # NER
            entities = await self.ner.extract(text)
            from .ner_extractor import filter_entities
            entities = filter_entities(entities)

            # Scoring
            score_result = self.scorer.score(
                titulo=titulo,
                resumo=resumo,
                fonte_tier=payload.get("fonte_tier", payload.get("tier", "padrao")),
                data_pub=payload.get("data_publicacao"),
                entities=entities,
            )

            wp_id = CATEGORY_TO_WP_ID.get(editoria, 1)

            return {
                **payload,
                "editoria": editoria,
                "categoria_wp_id": wp_id,
                "relevancia_score": score_result["score"],
                "urgencia": score_result["urgencia"],
                "entidades": entities,
                "confianca_classificacao": confidence,
            }
        except Exception:
            logger.error("Falha na pipeline de classificação", exc_info=True)
            raise

    async def _llm_classify(self, titulo: str, resumo: str) -> Optional[str]:
        """Fallback LLM para classificação de baixa confiança."""
        try:
            categories = list(CATEGORY_TO_WP_ID.keys())
            request = LLMRequest(
                task_type="classificacao_categoria",
                messages=[{
                    "role": "user",
                    "content": (
                        f"Classifique esta notícia em UMA das categorias: {', '.join(categories)}.\n\n"
                        f"Título: {titulo}\nResumo: {resumo[:300]}\n\n"
                        f"Responda APENAS com o nome da categoria, sem explicação."
                    ),
                }],
                max_tokens=50,
                temperature=0.1,
            )
            response = await self.router.route_request(request)
            category = response.content.strip().lower().replace(" ", "_")
            if category in CATEGORY_TO_WP_ID:
                return category
            # Tenta matching parcial
            for cat in categories:
                if cat in category or category in cat:
                    return cat
            return None
        except Exception:
            logger.warning("LLM fallback de classificação falhou", exc_info=True)
            return None
