"""Scoring objetivo + editorial para candidatos da homepage."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from shared.schemas import LLMRequest


def objective_score(candidate: dict) -> float:
    """Score local 0-50 baseado em recência, urgência e fonte."""

    score = 0.0
    urgencia = str(candidate.get("urgencia", "normal"))
    if urgencia == "breaking":
        score += 25
    elif urgencia == "alta":
        score += 15
    else:
        score += 8

    fonte_tier = int(candidate.get("fonte_tier", 2))
    score += max(0, 15 - (fonte_tier - 1) * 4)

    published = candidate.get("date_gmt")
    if isinstance(published, str) and published:
        try:
            dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_h = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600)
            score += max(0, 10 - min(10, age_h))
        except ValueError:
            score += 2

    return round(min(50.0, score), 2)


async def editorial_score(router, candidates: list[dict]) -> dict[int, float]:
    """Pontua candidatos com LLM PREMIUM (homepage_scoring)."""

    if not candidates:
        return {}

    request = LLMRequest(
        task_type="homepage_scoring",
        messages=[
            {
                "role": "system",
                "content": (
                    "Você é editor-chefe de homepage. Dê nota 0-50 para cada candidato, "
                    "considerando impacto nacional, utilidade pública, relevância e diversidade editorial."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Retorne JSON no formato {\"scores\": [{\"post_id\": int, \"score\": float}]}.\n\n"
                    f"Candidatos: {json.dumps(candidates, ensure_ascii=False)}"
                ),
            },
        ],
        temperature=0.1,
        max_tokens=1200,
        response_format={"type": "json_object"},
    )
    response = await router.route_request(request)
    payload = json.loads(response.content)
    out: dict[int, float] = {}
    for item in payload.get("scores", []):
        post_id = int(item["post_id"])
        out[post_id] = float(item["score"])
    return out
