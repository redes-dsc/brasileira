"""Pipeline de classificação: ML + NER + relevância + produção Kafka."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

from .classifier import MLClassifier
from .ner_extractor import NERExtractor, filter_entities
from .relevance_scorer import RelevanceScorer

CATEGORY_TO_WP_ID = {
    "politica": 2,
    "economia": 3,
    "esportes": 4,
    "tecnologia": 5,
    "saude": 6,
    "educacao": 7,
    "ciencia": 8,
    "cultura_entretenimento": 9,
    "mundo_internacional": 10,
    "meio_ambiente": 11,
    "seguranca_justica": 12,
    "sociedade": 13,
    "brasil": 14,
    "regionais": 15,
    "opiniao_analise": 16,
    "ultimas_noticias": 17,
}


@dataclass(slots=True)
class RawArticle:
    article_id: str
    url: str
    url_hash: str
    fonte_id: int
    fonte_nome: str
    fonte_tipo: str
    fonte_peso: int
    fonte_url: str
    fonte_categoria_hint: str
    titulo: str
    conteudo_bruto: str
    conteudo_html: str
    resumo: str
    imagem_url: str | None
    tipo: str
    data_publicacao: datetime
    data_coleta: datetime


@dataclass(slots=True)
class ClassifiedArticle:
    article_id: str
    categoria: str
    categoria_wp_id: int
    categoria_confidence: float
    score_relevancia: float
    urgencia: str
    tags_sugeridas: list[str]
    entidades_pessoas: list[str]
    entidades_orgs: list[str]
    entidades_locais: list[str]
    classificador_version: str


class ClassificationPipeline:
    """Orquestra classificação e produz mensagem classificada."""

    def __init__(
        self,
        ml_classifier: MLClassifier,
        ner_extractor: NERExtractor,
        relevance_scorer: RelevanceScorer,
        producer=None,
        llm_fallback=None,
    ):
        self.ml_classifier = ml_classifier
        self.ner_extractor = ner_extractor
        self.relevance_scorer = relevance_scorer
        self.producer = producer
        self.llm_fallback = llm_fallback

    async def classify(self, raw: RawArticle) -> ClassifiedArticle:
        classification = await self.ml_classifier.classify(
            titulo=raw.titulo,
            conteudo=raw.conteudo_bruto or raw.resumo,
            fonte_categoria_hint=raw.fonte_categoria_hint,
        )

        entities = await self.ner_extractor.extract(raw.titulo, raw.conteudo_bruto or raw.resumo)
        entities = filter_entities(entities)

        relevance = self.relevance_scorer.score(
            titulo=raw.titulo,
            conteudo=raw.conteudo_bruto or raw.resumo,
            fonte_tier=raw.fonte_tipo,
            fonte_peso=raw.fonte_peso,
            categoria=classification.categoria,
            data_publicacao=raw.data_publicacao,
        )

        category = classification.categoria
        confidence = classification.confianca
        if confidence < 0.55 and self.llm_fallback is not None:
            fallback = await self.llm_fallback(raw)
            if fallback in CATEGORY_TO_WP_ID:
                category = fallback

        classified = ClassifiedArticle(
            article_id=raw.article_id,
            categoria=category,
            categoria_wp_id=CATEGORY_TO_WP_ID.get(category, 17),
            categoria_confidence=confidence,
            score_relevancia=relevance.score,
            urgencia=relevance.urgencia.value,
            tags_sugeridas=entities.tags_wordpress,
            entidades_pessoas=entities.pessoas,
            entidades_orgs=entities.organizacoes,
            entidades_locais=entities.locais,
            classificador_version="3.0.0",
        )

        if self.producer is not None:
            await self.producer.send(
                "classified-articles",
                {
                    "article_id": classified.article_id,
                    "categoria": classified.categoria,
                    "categoria_wp_id": classified.categoria_wp_id,
                    "categoria_confidence": classified.categoria_confidence,
                    "score_relevancia": classified.score_relevancia,
                    "urgencia": classified.urgencia,
                    "tags_sugeridas": classified.tags_sugeridas,
                    "entidades_pessoas": classified.entidades_pessoas,
                    "entidades_orgs": classified.entidades_orgs,
                    "entidades_locais": classified.entidades_locais,
                    "classificador_version": classified.classificador_version,
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                },
                key=raw.article_id,
            )

        return classified
