"""Extrator de entidades simples para pipeline de classificação."""

from __future__ import annotations

import re
from dataclasses import dataclass

STOP_ORGS = {"governo", "empresa", "empresas", "federal", "estadual"}


@dataclass(slots=True)
class ExtractedEntities:
    pessoas: list[str]
    organizacoes: list[str]
    locais: list[str]
    entidade_principal: str | None
    tags_wordpress: list[str]


class NERExtractor:
    """NER leve baseado em padrões para português."""

    async def initialize(self) -> None:
        """Hook assíncrono para compatibilidade."""

    async def extract(self, titulo: str, conteudo: str) -> ExtractedEntities:
        text = f"{titulo}. {conteudo}"

        people_matches = re.findall(r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]+(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]+){0,2})", text)
        org_matches = re.findall(r"\b(STF|STJ|PF|Petrobras|INPE|ONU|Senado Federal|Câmara dos Deputados|Polícia Federal)\b", text)
        place_matches = re.findall(r"\b(Brasília|São Paulo|Rio de Janeiro|Porto Alegre|Amazônia|Brasil)\b", text)

        pessoas = list(dict.fromkeys(people_matches))[:10]
        organizacoes = list(dict.fromkeys(org_matches))[:10]
        locais = list(dict.fromkeys(place_matches))[:10]

        tags = list(dict.fromkeys((pessoas + organizacoes + locais)))[:5]
        entidade_principal = tags[0] if tags else None

        return ExtractedEntities(
            pessoas=pessoas,
            organizacoes=organizacoes,
            locais=locais,
            entidade_principal=entidade_principal,
            tags_wordpress=tags,
        )


def filter_entities(entities: ExtractedEntities) -> ExtractedEntities:
    """Filtra entidades genéricas para reduzir ruído."""

    orgs = [org for org in entities.organizacoes if org.lower() not in STOP_ORGS]
    tags = [tag for tag in entities.tags_wordpress if tag.lower() not in STOP_ORGS][:5]
    return ExtractedEntities(
        pessoas=entities.pessoas,
        organizacoes=orgs,
        locais=entities.locais,
        entidade_principal=entities.entidade_principal,
        tags_wordpress=tags,
    )
