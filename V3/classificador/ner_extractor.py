"""Extração de Entidades Nomeadas (NER) com spaCy + fallback regex."""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

_nlp = None
_NER_MODE = "regex"  # "spacy" or "regex"

STOP_ENTITIES = frozenset({
    "Foto", "Imagem", "Reprodução", "Agência", "Reuters", "AFP",
    "Leia Mais", "Saiba Mais", "Veja Também", "Fonte", "Crédito",
})


async def initialize_ner() -> str:
    """Tenta carregar spaCy, retorna modo usado."""
    global _nlp, _NER_MODE
    try:
        import spacy
        _nlp = spacy.load("pt_core_news_lg")
        _NER_MODE = "spacy"
        logger.info("NER: spaCy pt_core_news_lg carregado")
    except (ImportError, OSError):
        try:
            import spacy
            _nlp = spacy.load("pt_core_news_sm")
            _NER_MODE = "spacy"
            logger.info("NER: spaCy pt_core_news_sm carregado (fallback)")
        except (ImportError, OSError):
            _NER_MODE = "regex"
            logger.warning("NER: spaCy indisponível, usando regex fallback")
    return _NER_MODE


class NERExtractor:
    """Extrai entidades nomeadas do texto."""

    def __init__(self):
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        await initialize_ner()
        self._initialized = True

    async def extract(self, text: str) -> dict[str, list[str]]:
        """Extrai entidades: pessoas, organizações, locais."""
        if not self._initialized:
            await self.initialize()

        if _NER_MODE == "spacy" and _nlp is not None:
            return self._extract_spacy(text)
        return self._extract_regex(text)

    def _extract_spacy(self, text: str) -> dict[str, list[str]]:
        """Extração via spaCy NER."""
        doc = _nlp(text[:5000])
        entities: dict[str, list[str]] = {"pessoas": [], "organizacoes": [], "locais": []}

        for ent in doc.ents:
            name = ent.text.strip()
            if name in STOP_ENTITIES or len(name) < 2:
                continue
            if ent.label_ == "PER":
                if name not in entities["pessoas"]:
                    entities["pessoas"].append(name)
            elif ent.label_ == "ORG":
                if name not in entities["organizacoes"]:
                    entities["organizacoes"].append(name)
            elif ent.label_ in ("LOC", "GPE"):
                if name not in entities["locais"]:
                    entities["locais"].append(name)

        return entities

    def _extract_regex(self, text: str) -> dict[str, list[str]]:
        """Fallback regex para NER."""
        entities: dict[str, list[str]] = {"pessoas": [], "organizacoes": [], "locais": []}

        # Organizações comuns brasileiras
        org_patterns = [
            r"\b(STF|STJ|TSE|TST|TCU|CGU|MPF|PF|PRF)\b",
            r"\b(Petrobras|Itaú|Bradesco|Banco do Brasil|Caixa|BNDES|Vale|Embraer)\b",
            r"\b(Ibama|Anvisa|ANP|Anatel|Aneel|INSS|INPE|Fiocruz|Embrapa)\b",
            r"\b(ONU|OMS|FMI|Banco Mundial|Otan|Mercosul|Brics)\b",
            r"\b(PT|PSDB|MDB|PL|PP|PDT|PSB|PSOL|Podemos|União Brasil)\b",
        ]
        for pattern in org_patterns:
            for match in re.finditer(pattern, text):
                name = match.group()
                if name not in entities["organizacoes"]:
                    entities["organizacoes"].append(name)

        # Locais brasileiros comuns
        loc_patterns = [
            r"\b(São Paulo|Rio de Janeiro|Brasília|Belo Horizonte|Salvador|Curitiba|Fortaleza|Recife|Porto Alegre|Manaus|Belém|Goiânia)\b",
            r"\b(Brasil|Estados Unidos|China|Argentina|Rússia|Ucrânia|Israel|Palestina|Irã|Índia)\b",
        ]
        for pattern in loc_patterns:
            for match in re.finditer(pattern, text):
                name = match.group()
                if name not in entities["locais"]:
                    entities["locais"].append(name)

        return entities


def filter_entities(entities: dict[str, list[str]], max_per_type: int = 10) -> dict[str, list[str]]:
    """Filtra e limita entidades."""
    return {k: v[:max_per_type] for k, v in entities.items()}
