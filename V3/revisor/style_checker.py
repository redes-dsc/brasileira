"""Verificador de estilo jornalístico para ajustes seguros."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class StyleChange:
    """Representa uma mudança de estilo no título/resumo."""

    campo: str
    original: str
    corrigido: str
    motivo: str


class StyleChecker:
    """Padroniza capitalização e reduz excesso de exclamação."""

    def revisar_titulo(self, titulo: str) -> tuple[str, list[StyleChange]]:
        """Ajusta título mantendo sentido editorial."""

        changes: list[StyleChange] = []
        novo = titulo.strip()
        if "!!" in novo:
            original = novo
            novo = novo.replace("!!", "!")
            changes.append(StyleChange("title", original, novo, "redução de pontuação excessiva"))

        if novo and novo[0].islower():
            original = novo
            novo = novo[0].upper() + novo[1:]
            changes.append(StyleChange("title", original, novo, "capitalização inicial"))

        return novo, changes

    def revisar_resumo(self, resumo: str) -> tuple[str, list[StyleChange]]:
        """Remove bordas de whitespace no resumo."""

        cleaned = resumo.strip()
        if cleaned != resumo:
            return cleaned, [StyleChange("excerpt", resumo, cleaned, "remoção de espaços laterais")]
        return cleaned, []
