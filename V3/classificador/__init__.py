"""Classificador de artigos V3."""

from .classifier import MLClassifier
from .ner_extractor import NERExtractor, filter_entities
from .relevance_scorer import RelevanceScorer, Urgencia
from .pipeline import ClassificationPipeline

__all__ = [
    "MLClassifier",
    "NERExtractor",
    "filter_entities",
    "RelevanceScorer",
    "Urgencia",
    "ClassificationPipeline",
]
