"""Classificador de artigos V3."""

from .classifier import MLClassifier
from .ner_extractor import NERExtractor, NERResult, extract_entities, filter_entities
from .relevance_scorer import RelevanceScorer
from .pipeline import ClassificationPipeline

__all__ = [
    "MLClassifier",
    "NERExtractor",
    "NERResult",
    "extract_entities",
    "filter_entities",
    "RelevanceScorer",
    "ClassificationPipeline",
]
