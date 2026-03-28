"""Detector de relacionamento temático para matérias."""

from __future__ import annotations

import re
from collections import Counter


class TopicDetector:
    """Detector lexical simples para agrupamento inicial."""

    _WORD = re.compile(r"[a-zA-ZÀ-ÿ]{3,}")

    def tokens(self, text: str) -> list[str]:
        return [w.lower() for w in self._WORD.findall(text)]

    def related_score(self, tema_keywords: list[str], texto: str) -> float:
        """Retorna score [0,1] por overlap lexical."""

        base = {k.lower() for k in tema_keywords if k}
        if not base:
            return 0.0
        tokens = Counter(self.tokens(texto))
        overlap = sum(1 for k in base if k in tokens)
        return round(min(1.0, overlap / max(1, len(base))), 4)
