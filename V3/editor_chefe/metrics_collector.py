"""Coleta de métricas de fim de pipeline."""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Optional

from .config import MACROCATEGORIAS_16
from .schemas import CategoryMetrics

logger = logging.getLogger(__name__)

# Mapeamento reverso: WP category ID -> slug de macrocategoria.
# Estes IDs correspondem às categorias do WP blog_id=7 (brasileira.news).
# Quando o ID não é encontrado, cai em "ultimas_noticias".
WP_CATEGORY_ID_TO_SLUG: dict[int, str] = {
    2: "ultimas_noticias",
    3: "politica",
    4: "economia",
    5: "esportes",
    6: "tecnologia",
    7: "saude",
    8: "educacao",
    9: "ciencia",
    10: "cultura_entretenimento",
    11: "mundo_internacional",
    12: "meio_ambiente",
    13: "seguranca_justica",
    14: "sociedade",
    15: "brasil",
    16: "regionais",
    17: "opiniao_analise",
}


class MetricsCollector:
    """Consolida eventos publicados em métricas por categoria."""

    def __init__(self, wp_client: Optional[Any] = None) -> None:
        self._wp_client = wp_client

    def _wp_category_to_slug(self, wp_cat_ids: list[int]) -> str:
        """Converte lista de IDs de categoria WP para slug de macrocategoria."""
        for cat_id in wp_cat_ids:
            slug = WP_CATEGORY_ID_TO_SLUG.get(cat_id)
            if slug and slug in MACROCATEGORIAS_16:
                return slug
        return "ultimas_noticias"

    async def _fetch_events_from_wp(self) -> list[dict]:
        """Busca posts recentes do WP REST API e converte para eventos."""
        if self._wp_client is None:
            return []
        try:
            posts: list[Any] = await self._wp_client.get(
                "/wp-json/wp/v2/posts",
                params={
                    "per_page": 100,
                    "orderby": "date",
                    "order": "desc",
                    "status": "publish",
                },
            )
            if not isinstance(posts, list):
                logger.warning("WP REST API retornou formato inesperado: %s", type(posts))
                return []

            now = datetime.now(timezone.utc)
            events: list[dict] = []
            for post in posts:
                date_str = post.get("date_gmt", "")
                if not date_str:
                    continue
                try:
                    # WP retorna formato ISO sem timezone; é UTC
                    pub_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    if pub_date.tzinfo is None:
                        pub_date = pub_date.replace(tzinfo=timezone.utc)
                    idade_horas = (now - pub_date).total_seconds() / 3600.0
                except (ValueError, TypeError):
                    idade_horas = 9999.0

                wp_cat_ids = post.get("categories", [])
                categoria = self._wp_category_to_slug(wp_cat_ids)
                events.append({
                    "categoria": categoria,
                    "idade_horas": idade_horas,
                    "wp_post_id": post.get("id"),
                })
            logger.info("MetricsCollector: %d posts recentes obtidos do WP REST API", len(events))
            return events
        except Exception:
            logger.exception("Falha ao buscar posts do WP REST API para métricas")
            return []

    async def collect(self, published_events: Optional[list[dict]] = None) -> list[CategoryMetrics]:
        events = published_events or []

        # Se não recebeu eventos explícitos, buscar do WP REST API
        if not events and self._wp_client is not None:
            events = await self._fetch_events_from_wp()

        by_cat_1h: Counter[str] = Counter()
        by_cat_24h: Counter[str] = Counter()
        min_hours_since_last: dict[str, float] = {categoria: 9999.0 for categoria in MACROCATEGORIAS_16}

        for event in events:
            categoria = str(event.get("categoria", "ultimas_noticias"))
            idade_horas = float(event.get("idade_horas", 0.0))
            if idade_horas <= 1.0:
                by_cat_1h[categoria] += 1
            if idade_horas <= 24.0:
                by_cat_24h[categoria] += 1
            if categoria in min_hours_since_last and idade_horas < min_hours_since_last[categoria]:
                min_hours_since_last[categoria] = idade_horas

        metrics: list[CategoryMetrics] = []
        for categoria in MACROCATEGORIAS_16:
            p24 = by_cat_24h[categoria]
            score = min(p24 / 24.0, 1.0)
            metrics.append(
                CategoryMetrics(
                    categoria=categoria,
                    publicados_1h=by_cat_1h[categoria],
                    publicados_24h=p24,
                    horas_desde_ultimo=min_hours_since_last[categoria],
                    score_cobertura=score,
                )
            )
        return metrics
