"""Extração de Entidades Nomeadas com spaCy."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

_nlp = None

STOP_ENTITIES = frozenset({
    "Foto", "Imagem", "Reprodução", "Agência", "Reuters", "AFP",
    "Leia Mais", "Saiba Mais", "Veja Também", "Fonte", "Crédito",
})


def _get_nlp():
    global _nlp
    if _nlp is None:
        import spacy
        try:
            _nlp = spacy.load("pt_core_news_lg")
        except OSError:
            logger.warning("pt_core_news_lg não encontrado, usando pt_core_news_sm")
            try:
                _nlp = spacy.load("pt_core_news_sm")
            except OSError:
                logger.error("Nenhum modelo spaCy pt instalado")
                return None
    return _nlp


def extract_entities(text: str) -> dict[str, list[str]]:
    """Extrai entidades nomeadas do texto.

    Retorna dict com chaves PER, ORG, LOC, MISC.
    Cada valor é uma lista de entidades únicas.
    """
    nlp = _get_nlp()
    if nlp is None:
        return {"PER": [], "ORG": [], "LOC": [], "MISC": []}

    # Limitar texto para performance
    doc = nlp(text[:5000])

    entities: dict[str, set[str]] = {
        "PER": set(),
        "ORG": set(),
        "LOC": set(),
        "MISC": set(),
    }

    for ent in doc.ents:
        label = ent.label_
        name = ent.text.strip()

        if len(name) < 2 or name in STOP_ENTITIES:
            continue

        if label == "PER":
            entities["PER"].add(name)
        elif label == "ORG":
            entities["ORG"].add(name)
        elif label in ("LOC", "GPE"):
            entities["LOC"].add(name)
        else:
            entities["MISC"].add(name)

    return {k: sorted(v) for k, v in entities.items()}


@dataclass
class NERResult:
    """Resultado de NER para o pipeline e consumidores (formato legado em português)."""

    pessoas: list[str]
    organizacoes: list[str]
    locais: list[str]
    misc: list[str]
    entidade_principal: Optional[str]
    tags_wordpress: list[str]


def _raw_to_ner_result(raw: dict[str, list[str]]) -> NERResult:
    pessoas = list(raw["PER"])
    organizacoes = list(raw["ORG"])
    locais = list(raw["LOC"])
    misc = list(raw["MISC"])

    entidade_principal: Optional[str] = None
    if pessoas:
        entidade_principal = pessoas[0]
    elif organizacoes:
        entidade_principal = organizacoes[0]
    elif locais:
        entidade_principal = locais[0]

    tags: list[str] = []
    for pool in (pessoas, organizacoes, locais):
        for x in pool:
            if len(tags) >= 5:
                break
            if x not in tags:
                tags.append(x)
        if len(tags) >= 5:
            break

    return NERResult(
        pessoas=pessoas,
        organizacoes=organizacoes,
        locais=locais,
        misc=misc,
        entidade_principal=entidade_principal,
        tags_wordpress=tags[:5],
    )


def filter_entities(entities: NERResult, max_per_type: int = 10) -> NERResult:
    """Filtra stoplist, limita por tipo e remove falsos positivos comuns em ORG."""

    def trim(lst: list[str]) -> list[str]:
        out: list[str] = []
        for x in lst:
            if len(out) >= max_per_type:
                break
            if x in STOP_ENTITIES:
                continue
            out.append(x)
        return out

    pessoas = trim(entities.pessoas)
    locais = trim(entities.locais)
    misc = trim(entities.misc)
    organizacoes: list[str] = []
    for o in trim(entities.organizacoes):
        if o == "Governo":
            continue
        if o in STOP_ENTITIES:
            continue
        organizacoes.append(o)

    entidade_principal = entities.entidade_principal
    if entidade_principal == "Governo":
        entidade_principal = None
        if pessoas:
            entidade_principal = pessoas[0]
        elif organizacoes:
            entidade_principal = organizacoes[0]
        elif locais:
            entidade_principal = locais[0]

    # Recalcular tags_wordpress a partir das listas filtradas
    tags: list[str] = []
    for pool in (pessoas, organizacoes, locais):
        for x in pool:
            if len(tags) >= 5:
                break
            if x not in tags:
                tags.append(x)
        if len(tags) >= 5:
            break

    return NERResult(
        pessoas=pessoas,
        organizacoes=organizacoes,
        locais=locais,
        misc=misc,
        entidade_principal=entidade_principal,
        tags_wordpress=tags[:5],
    )


class NERExtractor:
    """Extrai entidades nomeadas do texto (spaCy), com interface async para o pipeline."""

    def __init__(self) -> None:
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _get_nlp)
        self._initialized = True

    async def extract(
        self,
        text: str = "",
        *,
        titulo: str = "",
        conteudo: str = "",
    ) -> NERResult:
        """Extrai entidades. Aceita `text` ou `titulo`/`conteudo` (como nos testes)."""
        if not self._initialized:
            await self.initialize()
        if titulo or conteudo:
            text = f"{titulo}. {conteudo}".strip()
        if not text:
            return NERResult(
                pessoas=[],
                organizacoes=[],
                locais=[],
                misc=[],
                entidade_principal=None,
                tags_wordpress=[],
            )

        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(None, extract_entities, text)
        return _raw_to_ner_result(raw)
