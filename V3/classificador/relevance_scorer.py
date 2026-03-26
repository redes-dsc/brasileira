"""Scoring de relevância e urgência para roteamento editorial."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum


class Urgencia(str, Enum):
    FLASH = "flash"
    NORMAL = "normal"
    ANALISE = "analise"


@dataclass(slots=True)
class RelevanceResult:
    score: float
    urgencia: Urgencia
    breakdown: dict[str, float]


class RelevanceScorer:
    """Calcula score 0-100 com fatores editoriais."""

    def score(
        self,
        titulo: str,
        conteudo: str,
        fonte_tier: str = "padrao",
        fonte_peso: int = 3,
        categoria: str | None = None,
        data_publicacao: datetime | None = None,
    ) -> RelevanceResult:
        now = datetime.now(timezone.utc)
        data = data_publicacao or now

        baseline = 35.0
        tier_bonus = {"governo": 20.0, "vip": 16.0, "padrao": 10.0, "nicho": 6.0}.get(fonte_tier, 8.0)
        peso_bonus = min(max(fonte_peso, 1), 5) * 4.0

        keywords = 0.0
        title_lower = titulo.lower()
        for marker in ("urgente", "exclusivo", "ao vivo", "recorde", "crise"):
            if marker in title_lower:
                keywords += 6.0

        age_hours = max((now - data).total_seconds() / 3600, 0.0)
        frescor = max(0.0, 20.0 - age_hours * 1.5)

        titulo_qualidade = 8.0 if len(titulo.split()) >= 6 else 4.0

        total = baseline + tier_bonus + peso_bonus + keywords + frescor + titulo_qualidade
        total = max(0.0, min(100.0, total))

        urgencia = Urgencia.NORMAL
        if "urgente" in title_lower or "última hora" in title_lower:
            urgencia = Urgencia.FLASH
        elif categoria == "opiniao_analise" or "análise" in title_lower or "analise" in title_lower:
            urgencia = Urgencia.ANALISE

        return RelevanceResult(
            score=round(total, 2),
            urgencia=urgencia,
            breakdown={
                "baseline": baseline,
                "tier_fonte": tier_bonus,
                "peso_fonte": peso_bonus,
                "keywords": keywords,
                "frescor": round(frescor, 2),
                "titulo_qualidade": titulo_qualidade,
                "score_final": round(total, 2),
            },
        )
