"""Verificador gramatical determinístico para correções rápidas."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(slots=True)
class TextChange:
    """Representa uma alteração textual simples."""

    campo: str
    original: str
    corrigido: str
    motivo: str


class GrammarChecker:
    """Aplica ajustes ortográficos e de pontuação de baixo risco."""

    _SUBS: tuple[tuple[str, str, str], ...] = (
        ("\u00e0 n\u00edvel de", "em", "locução inadequada"),
        ("afim de", "a fim de", "grafia correta"),
        ("a partir de agora", "a partir de agora", "normalização"),
    )

    def revisar(self, conteudo_html: str) -> tuple[str, list[TextChange]]:
        """Retorna HTML corrigido e lista de mudanças."""

        updated = conteudo_html
        changes: list[TextChange] = []

        for needle, repl, reason in self._SUBS:
            if needle in updated and needle != repl:
                updated = updated.replace(needle, repl)
                changes.append(TextChange("content", needle, repl, reason))

        compacted = re.sub(r"\s{2,}", " ", updated)
        if compacted != updated:
            changes.append(TextChange("content", "espaçamento irregular", "espaçamento normalizado", "normalização"))
            updated = compacted

        return updated, changes
