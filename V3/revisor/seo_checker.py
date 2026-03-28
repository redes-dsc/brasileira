"""Verificador SEO de baixa complexidade."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SEOChange:
    """Representa ajuste SEO em campo textual."""

    campo: str
    original: str
    corrigido: str
    motivo: str


class SEOChecker:
    """Garante limites práticos de título e descrição."""

    def revisar(self, titulo: str, resumo: str) -> tuple[str, str, list[SEOChange]]:
        """Retorna título, resumo e lista de alterações SEO."""

        changes: list[SEOChange] = []
        novo_titulo = titulo
        novo_resumo = resumo

        if len(novo_titulo) > 70:
            original = novo_titulo
            novo_titulo = novo_titulo[:67].rstrip() + "..."
            changes.append(SEOChange("title", original, novo_titulo, "título acima de 70 caracteres"))

        if len(novo_resumo) > 160:
            original = novo_resumo
            novo_resumo = novo_resumo[:157].rstrip() + "..."
            changes.append(SEOChange("excerpt", original, novo_resumo, "meta descrição acima de 160 caracteres"))

        return novo_titulo, novo_resumo, changes
