"""Scoring de relevância e urgência para roteamento editorial."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class RelevanceScorer:
    """Calcula score 0-100 com fatores editoriais e entity boost."""

    def score(
        self,
        titulo: str,
        resumo: str = "",
        fonte_tier: str = "padrao",
        data_pub: Optional[str] = None,
        entities: Optional[dict[str, list[str]]] = None,
    ) -> dict:
        """Calcula score de relevância retornando dict com score, urgencia, breakdown."""
        now = datetime.now(timezone.utc)
        data_publicacao = now
        if data_pub:
            try:
                data_publicacao = datetime.fromisoformat(data_pub.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                data_publicacao = now

        baseline = 35.0
        tier_bonus = {"governo": 20.0, "vip": 16.0, "padrao": 10.0, "nicho": 6.0, "secundario": 4.0}.get(fonte_tier, 8.0)

        keywords_score = 0.0
        title_lower = titulo.lower()
        for marker in ("urgente", "exclusivo", "ao vivo", "recorde", "crise", "breaking"):
            if marker in title_lower:
                keywords_score += 6.0

        age_hours = max((now - data_publicacao).total_seconds() / 3600, 0.0)
        frescor = max(0.0, 20.0 - age_hours * 1.5)

        titulo_qualidade = 8.0 if len(titulo.split()) >= 6 else 4.0

        # Entity-based scoring boost
        entity_bonus = 0.0
        if entities:
            pessoas = entities.get("pessoas", [])
            organizacoes = entities.get("organizacoes", [])
            locais = entities.get("locais", [])
            total_entities = len(pessoas) + len(organizacoes) + len(locais)
            # Artigos com mais entidades reconhecidas tendem a ser mais relevantes
            entity_bonus = min(10.0, total_entities * 1.5)
            # Boost extra para organizações governamentais/importantes
            high_profile_orgs = {"STF", "STJ", "PF", "MPF", "Petrobras", "ONU", "OMS", "Anvisa"}
            for org in organizacoes:
                if org in high_profile_orgs:
                    entity_bonus += 2.0
            entity_bonus = min(15.0, entity_bonus)

        total = baseline + tier_bonus + keywords_score + frescor + titulo_qualidade + entity_bonus
        total = max(0.0, min(100.0, total))

        urgencia = "normal"
        if "urgente" in title_lower or "última hora" in title_lower or "breaking" in title_lower:
            urgencia = "flash"
        elif "análise" in title_lower or "analise" in title_lower or "opinião" in title_lower:
            urgencia = "analise"

        return {
            "score": round(total, 2),
            "urgencia": urgencia,
            "breakdown": {
                "baseline": baseline,
                "tier_fonte": tier_bonus,
                "keywords": keywords_score,
                "frescor": round(frescor, 2),
                "titulo_qualidade": titulo_qualidade,
                "entidades": round(entity_bonus, 2),
                "score_final": round(total, 2),
            },
        }
